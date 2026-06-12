"""
Router /platform — Sprint C (Painel Owner Paladino).

TODOS os endpoints exigem PLATFORM_OWNER (dependency no router).
Papéis PLATFORM_SUPPORT/BILLING/READONLY permanecem schema-only.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.core.deps import require_role
from app.infrastructure.db.models import Company, ImpersonationGrant, User
from app.infrastructure.db.models.audit_log import AuditLog
from app.infrastructure.db.session import get_db
from app.modules.platform import service
from app.modules.platform.schemas import (
    FlagUpdate,
    ImpersonationGrantCreate,
    RedispatchRequest,
    SettingUpdate,
    TenantStatusUpdate,
)

_platform_owner = require_role("PLATFORM_OWNER")

router = APIRouter(
    prefix="/platform",
    tags=["platform"],
    dependencies=[Depends(_platform_owner)],
)


def _company_row(c: Company) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "slug": c.slug,
        "status": c.status,
        "active": c.active,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _grant_row(g: ImpersonationGrant) -> dict:
    return {
        "grant_id": str(g.id),
        "company_id": str(g.company_id),
        "mode": g.mode,
        "reason": g.reason,
        "expires_at": g.expires_at.isoformat() if g.expires_at else None,
        "revoked_at": g.revoked_at.isoformat() if g.revoked_at else None,
        "created_at": g.created_at.isoformat() if g.created_at else None,
    }


# ── Tenants ──────────────────────────────────────────────────────────────────

@router.get("/tenants")
def list_tenants(
    status: Optional[str] = Query(None),
    created_after: Optional[datetime] = Query(None),
    search_name: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    companies = service.list_tenants(db, status, created_after, search_name)
    return {"items": [_company_row(c) for c in companies], "total": len(companies)}


@router.get("/tenants/{company_id}")
def get_tenant(company_id: UUID, db: Session = Depends(get_db)):
    return _company_row(service._get_company_or_404(db, company_id))


@router.get("/tenants/{company_id}/health")
def get_tenant_health(company_id: UUID, db: Session = Depends(get_db)):
    return service.get_tenant_health(db, company_id)


@router.patch("/tenants/{company_id}/status")
def update_tenant_status(
    company_id: UUID,
    body: TenantStatusUpdate,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    company = service.set_tenant_status(db, company_id, body.status, body.reason, actor.id)
    return _company_row(company)


# ── Impersonation ────────────────────────────────────────────────────────────

@router.post("/impersonation/grants", status_code=201)
def create_impersonation_grant(
    body: ImpersonationGrantCreate,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    grant, grant_id = service.create_impersonation_grant(
        db, actor.id, body.company_id, body.mode, body.reason, body.duration_minutes
    )
    return {
        "grant_id": grant_id,
        "expires_at": grant.expires_at.isoformat(),
        "mode": grant.mode,
    }


@router.delete("/impersonation/grants/{grant_id}")
def revoke_impersonation_grant(
    grant_id: UUID,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    grant = service.revoke_impersonation_grant(db, grant_id, actor.id)
    return _grant_row(grant)


@router.get("/impersonation/grants")
def list_impersonation_grants(
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    grants = service.list_active_grants(db, actor.id)
    return {"items": [_grant_row(g) for g in grants], "total": len(grants)}


# ── Feature flags por tenant ─────────────────────────────────────────────────

@router.get("/tenants/{company_id}/flags")
def get_tenant_flags(company_id: UUID, db: Session = Depends(get_db)):
    return {"flags": service.get_tenant_flags(db, company_id)}


@router.put("/tenants/{company_id}/flags/{key}")
def set_tenant_flag(
    company_id: UUID,
    key: str,
    body: FlagUpdate,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    flags = service.set_tenant_flag(db, company_id, key, body.value, actor.id)
    return {"flags": flags}


# ── Platform settings (globais) ──────────────────────────────────────────────

@router.get("/settings")
def get_platform_settings(db: Session = Depends(get_db)):
    return {"settings": service.get_platform_settings(db)}


@router.put("/settings/{key}")
def set_platform_setting(
    key: str,
    body: SettingUpdate,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    return service.set_platform_setting(db, key, body.value, actor.id)


# ── Audit cross-tenant (RBAC-4: o acesso ao audit é auditado) ───────────────

@router.get("/audit")
def platform_audit(
    request: Request,
    company_id: Optional[UUID] = Query(None),
    actor_id: Optional[UUID] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    q = db.query(AuditLog)
    if company_id:
        q = q.filter(AuditLog.company_id == company_id)
    if actor_id:
        q = q.filter(AuditLog.actor_id == actor_id)
    if action:
        q = q.filter(AuditLog.action == action)
    if date_from:
        q = q.filter(AuditLog.occurred_at >= date_from)
    if date_to:
        q = q.filter(AuditLog.occurred_at <= date_to)
    q = q.order_by(AuditLog.occurred_at.desc())

    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()

    # RBAC-4: acesso ao audit é ele mesmo auditado — ANTES de retornar dados.
    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role=actor.role,
            action="platform_audit_access",
            resource_type="AuditLog",
            after_snapshot={
                "filters": {k: str(v) for k, v in dict(request.query_params).items()},
                "result_count": len(items),
            },
        ),
        db,
    )
    db.commit()

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
        }

    return {"total": total, "page": page, "limit": limit, "items": [_row(i) for i in items]}


# ── Redispatch de comunicação (Decisão D7) ───────────────────────────────────

@router.post("/communications/{log_id}/redispatch")
def redispatch_communication(
    log_id: UUID,
    body: RedispatchRequest,
    actor: User = Depends(_platform_owner),
    db: Session = Depends(get_db),
):
    new_log = service.redispatch_communication(db, log_id, body.reason, actor.id)
    return {
        "new_log_id": str(new_log.log_id),
        "status": new_log.status,
        "original_log_id": str(log_id),
    }
