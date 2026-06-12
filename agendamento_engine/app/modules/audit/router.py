import csv
import io
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.core.deps import require_role, get_current_user
from app.infrastructure.db.models import User
from app.infrastructure.db.models.audit_log import AuditLog
from app.infrastructure.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


def _build_query(db: Session, filters: dict):
    q = db.query(AuditLog)
    if filters.get("company_id"):
        q = q.filter(AuditLog.company_id == filters["company_id"])
    if filters.get("action"):
        q = q.filter(AuditLog.action == filters["action"])
    if filters.get("actor_id"):
        q = q.filter(AuditLog.actor_id == filters["actor_id"])
    if filters.get("date_from"):
        q = q.filter(AuditLog.occurred_at >= filters["date_from"])
    if filters.get("date_to"):
        q = q.filter(AuditLog.occurred_at <= filters["date_to"])
    return q.order_by(AuditLog.occurred_at.desc())


@router.get("/logs")
def list_audit_logs(
    company_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    # PLATFORM_OWNER pode filtrar por qualquer company_id;
    # outros papéis são restritos ao próprio tenant.
    effective_company_id = (
        company_id if actor.role == "PLATFORM_OWNER" else actor.company_id
    )

    filters = {
        "company_id": effective_company_id,
        "action": action,
        "actor_id": actor_id,
        "date_from": date_from,
        "date_to": date_to,
    }

    q = _build_query(db, filters)
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    def _row(log: AuditLog) -> dict:
        return {
            "audit_id": str(log.audit_id),
            "company_id": str(log.company_id) if log.company_id else None,
            "actor_id": str(log.actor_id),
            "actor_role": log.actor_role,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": str(log.resource_id) if log.resource_id else None,
            "reason": log.reason,
            "before_snapshot": log.before_snapshot,
            "after_snapshot": log.after_snapshot,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
            "ip_address": log.ip_address,
        }

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_row(item) for item in items],
    }


@router.get("/impersonation-accesses")
def list_impersonation_accesses(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    """Sprint C (B7): o tenant vê os acessos de impersonation no próprio audit.

    Registros gravados pelo ImpersonationMiddleware com
    action="impersonated_request" e company_id do tenant alvo.
    Requer JWT de tenant — PLATFORM_OWNER pode usar /platform/audit.
    """
    if actor.company_id is None:
        raise HTTPException(
            status_code=403,
            detail="Endpoint de tenant — use /platform/audit",
        )

    q = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == "impersonated_request",
            AuditLog.company_id == actor.company_id,
        )
        .order_by(AuditLog.occurred_at.desc())
    )
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    def _access_row(log: AuditLog) -> dict:
        return {
            "audit_id": str(log.audit_id),
            "grant_id": str(log.resource_id) if log.resource_id else None,
            "actor_id": str(log.actor_id),
            "reason": log.reason,
            "request": log.after_snapshot,
            "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
        }

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": [_access_row(item) for item in items],
    }


@router.get("/logs/export")
def export_audit_logs(
    company_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    actor: User = Depends(require_role("OWNER", "PLATFORM_OWNER")),
    db: Session = Depends(get_db),
):
    effective_company_id = (
        company_id if actor.role == "PLATFORM_OWNER" else actor.company_id
    )

    filters = {
        "company_id": effective_company_id,
        "action": action,
        "actor_id": actor_id,
        "date_from": date_from,
        "date_to": date_to,
    }

    # record_sensitive_action ANTES de retornar o stream (RBAC-4)
    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role=actor.role,
            action="export_audit",
            resource_type="AuditLog",
            company_id=actor.company_id,
            reason="export via API",
        ),
        db,
    )
    db.commit()

    logs = _build_query(db, filters).all()

    def _generate():
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "audit_id", "company_id", "actor_id", "actor_role",
            "action", "resource_type", "resource_id",
            "reason", "occurred_at", "ip_address",
        ])
        yield output.getvalue()
        output.seek(0)
        output.truncate()

        for log in logs:
            writer.writerow([
                str(log.audit_id),
                str(log.company_id) if log.company_id else "",
                str(log.actor_id),
                log.actor_role,
                log.action,
                log.resource_type,
                str(log.resource_id) if log.resource_id else "",
                log.reason or "",
                log.occurred_at.isoformat() if log.occurred_at else "",
                log.ip_address or "",
            ])
            yield output.getvalue()
            output.seek(0)
            output.truncate()

    return StreamingResponse(
        _generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
