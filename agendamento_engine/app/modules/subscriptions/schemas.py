from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SubscriptionPlanCreate(BaseModel):
    name: str
    cotas_per_cycle: int
    price: Decimal
    cycle_days: int = 30
    rollover_enabled: bool = False
    service_id: Optional[UUID] = None


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    cotas_per_cycle: Optional[int] = None
    price: Optional[Decimal] = None
    cycle_days: Optional[int] = None
    rollover_enabled: Optional[bool] = None
    service_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class SubscriptionPlanResponse(BaseModel):
    plan_id: UUID
    company_id: UUID
    name: str
    service_id: Optional[UUID]
    cotas_per_cycle: int
    price: Decimal
    cycle_days: int
    rollover_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class SubscribeRequest(BaseModel):
    customer_id: UUID
    plan_id: UUID
    first_billing_at: Optional[datetime] = None


class SubscriptionResponse(BaseModel):
    subscription_id: UUID
    company_id: UUID
    customer_id: UUID
    plan_id: UUID
    status: str
    next_billing_at: datetime
    overdue_since: Optional[datetime]
    paused_at: Optional[datetime]
    cancelled_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}
