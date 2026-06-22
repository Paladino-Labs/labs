from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PlanItemCreate(BaseModel):
    item_type: Literal["SERVICE", "PRODUCT"]
    service_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    quantity: int = Field(..., gt=0)

    @model_validator(mode="after")
    def _validate_target(self) -> "PlanItemCreate":
        if self.item_type == "SERVICE":
            if self.service_id is None or self.product_id is not None:
                raise ValueError("item SERVICE exige service_id (e product_id nulo)")
        else:  # PRODUCT
            if self.product_id is None or self.service_id is not None:
                raise ValueError("item PRODUCT exige product_id (e service_id nulo)")
        return self


class PlanItemResponse(BaseModel):
    item_id: UUID
    item_type: str
    service_id: Optional[UUID] = None
    service_name: Optional[str] = None
    product_id: Optional[UUID] = None
    product_name: Optional[str] = None
    quantity: int
    display_order: int

    model_config = {"from_attributes": True}


class SubscriptionPlanCreate(BaseModel):
    name: str
    items: List[PlanItemCreate] = Field(..., min_length=1)
    price: Decimal
    cycle_days: int = 30
    rollover_enabled: bool = False


class SubscriptionPlanUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    cycle_days: Optional[int] = None
    rollover_enabled: Optional[bool] = None
    is_active: Optional[bool] = None


class SubscriptionPlanResponse(BaseModel):
    plan_id: UUID
    company_id: UUID
    name: str
    items: List[PlanItemResponse]
    total_cotas_per_cycle: int
    price: Decimal
    cycle_days: int
    rollover_enabled: bool
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SubscribeRequest(BaseModel):
    customer_id: UUID
    plan_id: UUID
    payment_method: str = "manual"
    target_account_id: Optional[UUID] = None
    first_billing_at: Optional[datetime] = None


class SubscribeResponse(BaseModel):
    subscription_id: UUID
    payment_id: Optional[UUID] = None


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
