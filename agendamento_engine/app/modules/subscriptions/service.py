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
    plans = (
        db.query(SubscriptionPlan)
        .filter(SubscriptionPlan.company_id == company_id)
        .order_by(SubscriptionPlan.created_at.desc())
        .all()
    )
    return _attach_plan_item_names(db, plans)


def create_plan(
    company_id: UUID,
    name: str,
    items: list,  # List[PlanItemCreate] — item_type/service_id/product_id/quantity
    price,
    cycle_days: int = 30,
    rollover_enabled: bool = False,
    db: Optional[Session] = None,
) -> SubscriptionPlan:
    """Cria SubscriptionPlan + 1 PlanItem por item.
    cotas_per_cycle = sum(item.quantity) (coluna derivada, sincronizada na criação)."""
    from decimal import Decimal
    from app.infrastructure.db.models.subscription import PlanItem

    cotas_per_cycle = sum(item.quantity for item in items)
    plan = SubscriptionPlan(
        plan_id=uuid.uuid4(),
        company_id=company_id,
        name=name,
        cotas_per_cycle=cotas_per_cycle,
        price=Decimal(str(price)),
        cycle_days=cycle_days,
        rollover_enabled=rollover_enabled,
        is_active=True,
    )
    db.add(plan)
    db.flush()

    for order, item in enumerate(items):
        db.add(PlanItem(
            item_id=uuid.uuid4(),
            plan_id=plan.plan_id,
            company_id=company_id,
            item_type=item.item_type,
            service_id=item.service_id,
            product_id=item.product_id,
            quantity=item.quantity,
            display_order=order,
        ))

    db.commit()
    db.refresh(plan)
    return _attach_plan_item_names(db, [plan])[0]


def update_plan(plan_id: UUID, company_id: UUID, db: Session, **kwargs) -> SubscriptionPlan:
    plan = _get_plan_or_404(plan_id, company_id, db)
    allowed = {"name", "price", "cycle_days", "rollover_enabled", "is_active"}
    for field, value in kwargs.items():
        if field in allowed and value is not None:
            setattr(plan, field, value)
    plan.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(plan)
    return _attach_plan_item_names(db, [plan])[0]


def _attach_plan_item_names(db: Session, plans: List[SubscriptionPlan]) -> List[SubscriptionPlan]:
    """Anexa total_cotas_per_cycle + service_name/product_name de cada item
    como atributos transientes (batch, sem N+1) p/ serialização Pydantic."""
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.service import Service

    service_ids, product_ids = set(), set()
    for plan in plans:
        for item in plan.items:
            if item.service_id:
                service_ids.add(item.service_id)
            if item.product_id:
                product_ids.add(item.product_id)

    svc_names = {}
    if service_ids:
        svc_names = {
            s.id: s.name
            for s in db.query(Service).filter(Service.id.in_(service_ids)).all()
        }
    prod_names = {}
    if product_ids:
        prod_names = {
            p.id: p.name
            for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
        }

    for plan in plans:
        plan.total_cotas_per_cycle = sum(item.quantity for item in plan.items)
        for item in plan.items:
            item.service_name = svc_names.get(item.service_id)
            item.product_name = prod_names.get(item.product_id)
    return plans


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
    payment_method: str = "manual",
    target_account_id: Optional[UUID] = None,
    first_billing_at: Optional[datetime] = None,
):
    """Cria CustomerSubscription ACTIVE + primeiro Payment PENDING (mesmo request).

    Retorna (subscription, payment). O Payment PENDING vincula subscription_id;
    quando confirmado, o subscription_payment_handler gera os créditos do ciclo.
    """
    from decimal import Decimal

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
    db.flush()

    # Primeiro Payment (PENDING) — mesmo padrão do packages.purchase()
    from app.modules.payments import service as payment_service
    payment = payment_service.create_payment(
        company_id=company_id,
        customer_id=customer_id,
        gross_amount=Decimal(str(plan.price)),
        payment_method=payment_method,
        provider="manual",
        target_account_id=target_account_id,
        subscription_id=subscription.subscription_id,
        db=db,
    )

    db.commit()
    db.refresh(subscription)
    return subscription, payment


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
