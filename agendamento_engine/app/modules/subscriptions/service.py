"""SubscriptionEngine — Sprint 15.

subscribe():   cria CustomerSubscription ACTIVE.
pause()/resume()/cancel(): transições de estado.
Workers externos criam os Payments (renewal_worker) e gerenciam inadimplência (overdue_worker).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan

logger = logging.getLogger(__name__)


# ── Plans ─────────────────────────────────────────────────────────────────────

def list_plans(company_id: UUID, db: Session) -> List[SubscriptionPlan]:
    return (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.company_id == company_id)
        .order_by(SubscriptionPlan.created_at.desc())
        .all()
    )


def create_plan(
    company_id: UUID,
    name: str,
    cotas_per_cycle: int,
    price,
    cycle_days: int = 30,
    rollover_enabled: bool = False,
    service_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> SubscriptionPlan:
    from decimal import Decimal
    plan = SubscriptionPlan(
        plan_id=uuid.uuid4(),
        company_id=company_id,
        name=name,
        service_id=service_id,
        cotas_per_cycle=cotas_per_cycle,
        price=Decimal(str(price)),
        cycle_days=cycle_days,
        rollover_enabled=rollover_enabled,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    return plan


def update_plan(plan_id: UUID, company_id: UUID, db: Session, **kwargs) -> SubscriptionPlan:
    plan = _get_plan_or_404(plan_id, company_id, db)
    allowed = {"name", "cotas_per_cycle", "price", "cycle_days", "rollover_enabled", "service_id", "is_active"}
    for field, value in kwargs.items():
        if field in allowed and value is not None:
            setattr(plan, field, value)
    plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return plan


def _get_plan_or_404(plan_id: UUID, company_id: UUID, db: Session) -> SubscriptionPlan:
    plan = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.plan_id == plan_id,
        SubscriptionPlan.company_id == company_id,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Plano de assinatura não encontrado")
    return plan


# ── Subscriptions ─────────────────────────────────────────────────────────────

def subscribe(
    customer_id: UUID,
    plan_id: UUID,
    company_id: UUID,
    db: Session,
    first_billing_at: Optional[datetime] = None,
) -> CustomerSubscription:
    """Cria CustomerSubscription ACTIVE com next_billing_at = first_billing_at ou now()."""
    plan = _get_plan_or_404(plan_id, company_id, db)
    if not plan.is_active:
        raise HTTPException(status_code=422, detail="Plano de assinatura inativo")

    billing_at = first_billing_at or datetime.now(timezone.utc)

    subscription = CustomerSubscription(
        subscription_id=uuid.uuid4(),
        company_id=company_id,
        customer_id=customer_id,
        plan_id=plan_id,
        status="ACTIVE",
        next_billing_at=billing_at,
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def get_subscription(subscription_id: UUID, company_id: UUID, db: Session) -> CustomerSubscription:
    sub = db.query(CustomerSubscription).filter(
        CustomerSubscription.subscription_id == subscription_id,
        CustomerSubscription.company_id == company_id,
    ).first()
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")
    return sub


def list_subscriptions(
    company_id: UUID,
    db: Session,
    customer_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> List[CustomerSubscription]:
    q = db.query(CustomerSubscription).filter(CustomerSubscription.company_id == company_id)
    if customer_id:
        q = q.filter(CustomerSubscription.customer_id == customer_id)
    if status:
        q = q.filter(CustomerSubscription.status == status)
    return q.order_by(CustomerSubscription.created_at.desc()).all()


def pause(subscription_id: UUID, company_id: UUID, db: Session) -> CustomerSubscription:
    sub = get_subscription(subscription_id, company_id, db)
    if sub.status not in ("ACTIVE", "OVERDUE"):
        raise HTTPException(
            status_code=422,
            detail=f"Não é possível pausar assinatura com status={sub.status}",
        )
    sub.status = "PAUSED"
    sub.paused_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sub)
    return sub


def resume(subscription_id: UUID, company_id: UUID, db: Session) -> CustomerSubscription:
    sub = get_subscription(subscription_id, company_id, db)
    if sub.status != "PAUSED":
        raise HTTPException(
            status_code=422,
            detail=f"Não é possível retomar assinatura com status={sub.status}",
        )
    sub.status = "ACTIVE"
    sub.paused_at = None
    db.commit()
    db.refresh(sub)
    return sub


def cancel(subscription_id: UUID, company_id: UUID, db: Session) -> CustomerSubscription:
    sub = get_subscription(subscription_id, company_id, db)
    if sub.status == "CANCELLED":
        raise HTTPException(status_code=422, detail="Assinatura já cancelada")
    sub.status = "CANCELLED"
    sub.cancelled_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sub)
    return sub
