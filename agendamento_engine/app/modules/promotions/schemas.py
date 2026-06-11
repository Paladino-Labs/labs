from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PromotionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    discount_type: str  # PERCENTAGE | FIXED_AMOUNT | OVERRIDE_PRICE | FREE_ITEM
    discount_value: Optional[Decimal] = None
    application_mode: str = "AUTOMATIC"  # AUTOMATIC | COUPON_REQUIRED
    cumulative: bool = False
    priority: int = 0
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    max_uses: Optional[int] = None
    max_uses_per_customer: Optional[int] = None
    # {min_order_value?, service_ids?, product_ids?, subscription_cycle_number_in?,
    #  subscription_cycle_min?, subscription_cycle_max?, customer_classification?}
    conditions: Optional[dict] = None


class PromotionResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    description: Optional[str] = None
    discount_type: str
    discount_value: Optional[Decimal] = None
    application_mode: str
    cumulative: bool
    priority: int
    status: str
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    max_uses: Optional[int] = None
    max_uses_per_customer: Optional[int] = None
    uses_count: int
    conditions: Optional[dict] = None
    created_by: UUID
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CouponGenerateRequest(BaseModel):
    generation_type: str  # BULK | SINGLE_USE | PER_CUSTOMER
    quantity: int = 1     # apenas BULK
    code: Optional[str] = None    # código explícito (somente geração unitária)
    prefix: Optional[str] = None  # prefixo para códigos aleatórios
    max_uses: Optional[int] = None
    customer_id: Optional[UUID] = None  # obrigatório para PER_CUSTOMER
    expires_at: Optional[datetime] = None
    coupon_reopen_policy: str = "NEVER_REOPEN"  # NEVER_REOPEN | REOPEN_ON_REFUND


class CouponResponse(BaseModel):
    id: UUID
    company_id: UUID
    promotion_id: UUID
    code: str
    generation_type: str
    max_uses: Optional[int] = None
    uses_count: int
    coupon_reopen_policy: str
    status: str
    customer_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PreviewRequest(BaseModel):
    gross_amount: Decimal = Field(gt=0)
    service_ids: Optional[list[UUID]] = None
    product_ids: Optional[list[UUID]] = None
    customer_id: Optional[UUID] = None
    coupon_code: Optional[str] = None
    subscription_cycle: Optional[int] = None


class PreviewApplication(BaseModel):
    promotion_id: str
    sequence: int
    discount_type: str
    base_amount: str
    discount_amount: str


class PreviewResponse(BaseModel):
    final_amount: str
    discount_total: str
    applications: list[PreviewApplication]
    coupon_valid: bool
