from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.subscriptions import service as subscription_service
from app.modules.subscriptions.schemas import (
    SubscribeRequest,
    SubscriptionPlanCreate,
    SubscriptionPlanResponse,
    SubscriptionPlanUpdate,
    SubscriptionResponse,
)

router = APIRouter(tags=["subscriptions"])


@router.get("/subscription-plans", response_model=List[SubscriptionPlanResponse])
def list_plans(
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.list_plans(current_user.company_id, db)


@router.post("/subscription-plans", response_model=SubscriptionPlanResponse, status_code=201)
def create_plan(
    body: SubscriptionPlanCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.create_plan(
        company_id=current_user.company_id,
        name=body.name,
        cotas_per_cycle=body.cotas_per_cycle,
        price=body.price,
        cycle_days=body.cycle_days,
        rollover_enabled=body.rollover_enabled,
        service_id=body.service_id,
        db=db,
    )


@router.patch("/subscription-plans/{plan_id}", response_model=SubscriptionPlanResponse)
def update_plan(
    plan_id: UUID,
    body: SubscriptionPlanUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.update_plan(
        plan_id=plan_id,
        company_id=current_user.company_id,
        db=db,
        **body.model_dump(exclude_none=True),
    )


@router.get("/subscriptions", response_model=List[SubscriptionResponse])
def list_subscriptions(
    customer_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.list_subscriptions(
        company_id=current_user.company_id,
        db=db,
        customer_id=customer_id,
        status=status,
    )


@router.post("/subscriptions", response_model=SubscriptionResponse, status_code=201)
def create_subscription(
    body: SubscribeRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.subscribe(
        customer_id=body.customer_id,
        plan_id=body.plan_id,
        company_id=current_user.company_id,
        db=db,
        first_billing_at=body.first_billing_at,
    )


@router.get("/subscriptions/{subscription_id}", response_model=SubscriptionResponse)
def get_subscription(
    subscription_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.get_subscription(subscription_id, current_user.company_id, db)


@router.patch("/subscriptions/{subscription_id}/pause", response_model=SubscriptionResponse)
def pause_subscription(
    subscription_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.pause(subscription_id, current_user.company_id, db)


@router.patch("/subscriptions/{subscription_id}/resume", response_model=SubscriptionResponse)
def resume_subscription(
    subscription_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.resume(subscription_id, current_user.company_id, db)


@router.patch("/subscriptions/{subscription_id}/cancel", response_model=SubscriptionResponse)
def cancel_subscription(
    subscription_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return subscription_service.cancel(subscription_id, current_user.company_id, db)
