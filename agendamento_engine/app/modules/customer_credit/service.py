"""CustomerCredit — sistema de cotas de uso (Sprint 13).

FEFO (First Expired First Out): cota com vencimento mais próximo é consumida primeiro.
SELECT FOR UPDATE SKIP LOCKED garante atomicidade em consumos concorrentes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.infrastructure.db.models.customer_credit import CustomerCredit, CustomerCreditConsumption
from app.modules.customer_credit.exceptions import NoCreditAvailableError


def consume_for_operation(
    customer_id: UUID,
    appointment_id: Optional[UUID],
    company_id: UUID,
    db: Session,
) -> CustomerCreditConsumption:
    """
    FEFO: ORDER BY expires_at NULLS LAST, granted_at ASC.
    SELECT FOR UPDATE SKIP LOCKED — concorrência segura.
    Filtra: status=ACTIVE AND (expires_at IS NULL OR expires_at > now()).
    remaining_cotas -= 1.
    Se remaining_cotas == 0: status = EXHAUSTED.
    """
    now = datetime.now(timezone.utc)

    credit = (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.company_id == company_id,
            CustomerCredit.customer_id == customer_id,
            CustomerCredit.status == "ACTIVE",
            (CustomerCredit.expires_at == None) | (CustomerCredit.expires_at > now),
        )
        .order_by(
            CustomerCredit.expires_at.asc().nullslast(),
            CustomerCredit.granted_at.asc(),
        )
        .with_for_update(skip_locked=True)
        .first()
    )

    if credit is None:
        raise NoCreditAvailableError()

    credit.remaining_cotas -= 1
    if credit.remaining_cotas == 0:
        credit.status = "EXHAUSTED"

    consumption = CustomerCreditConsumption(
        consumption_id=uuid.uuid4(),
        credit_id=credit.credit_id,
        company_id=company_id,
        customer_id=customer_id,
        appointment_id=appointment_id,
        consumed_at=now,
    )
    db.add(consumption)
    db.flush()

    _publish_consumed(credit, consumption)

    return consumption


def _publish_consumed(credit: CustomerCredit, consumption: CustomerCreditConsumption) -> None:
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="customer_credit.consumed",
            occurred_at=datetime.now(timezone.utc),
            company_id=credit.company_id,
            idempotency_key=f"customer_credit.consumed:{consumption.consumption_id}",
            actor={"type": "SYSTEM", "id": None},
            payload={
                "credit_id": str(credit.credit_id),
                "consumption_id": str(consumption.consumption_id),
                "customer_id": str(credit.customer_id),
                "remaining_cotas": credit.remaining_cotas,
            },
        )
        event_bus.publish(event)
    except Exception:
        pass


def grant_cota(
    customer_id: UUID,
    total_cotas: int,
    expires_at: Optional[datetime],
    reason: str,
    actor_id: UUID,
    actor_role: str,
    company_id: UUID,
    db: Session,
) -> CustomerCredit:
    """
    Concessão manual (entitlement_type=GRANT_COTA).
    NÃO gera Movement/Entry — não é receita, é cortesia ou ajuste.
    record_sensitive_action obrigatório com reason.
    """
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="reason é obrigatório para grant_cota")

    credit = CustomerCredit(
        credit_id=uuid.uuid4(),
        company_id=company_id,
        customer_id=customer_id,
        entitlement_type="GRANT_COTA",
        source_id=None,
        total_cotas=total_cotas,
        remaining_cotas=total_cotas,
        status="ACTIVE",
        granted_at=datetime.now(timezone.utc),
        expires_at=expires_at,
    )
    db.add(credit)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role=actor_role,
            action="grant_cota",
            resource_type="customer_credit",
            resource_id=credit.credit_id,
            company_id=company_id,
            reason=reason,
        ),
        db,
    )

    return credit


def revoke(
    credit_id: UUID,
    reason: str,
    actor_id: UUID,
    actor_role: str,
    company_id: UUID,
    db: Session,
) -> CustomerCredit:
    """ACTIVE/EXHAUSTED → REVOKED."""
    credit = db.query(CustomerCredit).filter(
        CustomerCredit.credit_id == credit_id,
        CustomerCredit.company_id == company_id,
    ).first()

    if credit is None:
        raise HTTPException(status_code=404, detail="Crédito não encontrado")

    if credit.status not in ("ACTIVE", "EXHAUSTED"):
        raise HTTPException(
            status_code=422,
            detail=f"Não é possível revogar crédito com status={credit.status}",
        )

    credit.status = "REVOKED"
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role=actor_role,
            action="revoke_credit",
            resource_type="customer_credit",
            resource_id=credit_id,
            company_id=company_id,
            reason=reason,
        ),
        db,
    )

    _publish_revoked(credit)

    return credit


def _publish_revoked(credit: CustomerCredit) -> None:
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="customer_credit.revoked",
            occurred_at=datetime.now(timezone.utc),
            company_id=credit.company_id,
            idempotency_key=f"customer_credit.revoked:{credit.credit_id}",
            actor={"type": "SYSTEM", "id": None},
            payload={
                "credit_id": str(credit.credit_id),
                "customer_id": str(credit.customer_id),
            },
        )
        event_bus.publish(event)
    except Exception:
        pass


def get_balance(
    customer_id: UUID,
    company_id: UUID,
    db: Session,
) -> List[dict]:
    """Retorna lista de créditos ACTIVE com saldo, vencimento e origem."""
    now = datetime.now(timezone.utc)
    credits = (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.company_id == company_id,
            CustomerCredit.customer_id == customer_id,
            CustomerCredit.status == "ACTIVE",
            (CustomerCredit.expires_at == None) | (CustomerCredit.expires_at > now),
        )
        .order_by(
            CustomerCredit.expires_at.asc().nullslast(),
            CustomerCredit.granted_at.asc(),
        )
        .all()
    )

    return [
        {
            "credit_id": str(c.credit_id),
            "entitlement_type": c.entitlement_type,
            "total_cotas": c.total_cotas,
            "remaining_cotas": c.remaining_cotas,
            "status": c.status,
            "granted_at": c.granted_at.isoformat() if c.granted_at else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "source_id": str(c.source_id) if c.source_id else None,
        }
        for c in credits
    ]


def list_credits(
    customer_id: UUID,
    company_id: UUID,
    db: Session,
) -> List[CustomerCredit]:
    return (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.company_id == company_id,
            CustomerCredit.customer_id == customer_id,
        )
        .order_by(CustomerCredit.granted_at.desc())
        .all()
    )
