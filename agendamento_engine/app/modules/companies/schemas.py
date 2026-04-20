from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CompanySettingsResponse(BaseModel):
    slot_interval_minutes: int
    default_commission_percentage: Decimal
    max_advance_booking_days: int
    require_payment_upfront: bool
    bot_enabled: bool
    online_booking_enabled: bool

    model_config = {"from_attributes": True}


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    slug: Optional[str]
    active: bool
    settings: Optional[CompanySettingsResponse] = None

    model_config = {"from_attributes": True}


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    slug: Optional[str] = Field(None, min_length=1, max_length=100)


class CompanySettingsUpdate(BaseModel):
    slot_interval_minutes: Optional[int] = Field(None, ge=5, le=120)
    default_commission_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    max_advance_booking_days: Optional[int] = Field(None, ge=1, le=365)
    require_payment_upfront: Optional[bool] = None
    bot_enabled: Optional[bool] = None
    online_booking_enabled: Optional[bool] = None


class CompanyPatch(BaseModel):
    company: Optional[CompanyUpdate] = None
    settings: Optional[CompanySettingsUpdate] = None
