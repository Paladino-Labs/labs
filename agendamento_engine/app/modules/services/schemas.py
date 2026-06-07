from uuid import UUID
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class ServiceCreate(BaseModel):
    name: str
    price: Decimal
    duration: int  # minutos
    description: Optional[str] = None
    image_url: Optional[str] = None
    preparation_minutes_before: int = 0
    preparation_minutes_after: int = 0


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    duration: Optional[int] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None
    preparation_minutes_before: Optional[int] = None
    preparation_minutes_after: Optional[int] = None


class ServiceResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    price: Decimal
    duration: int
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: bool
    preparation_minutes_before: int = 0
    preparation_minutes_after: int = 0

    model_config = ConfigDict(from_attributes=True)


# ─── ServiceVariant ───────────────────────────────────────────────────────────

class ServiceVariantCreate(BaseModel):
    name: str
    price: Decimal
    duration_min: int
    sort_order: int = 0


class ServiceVariantUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    duration_min: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ServiceVariantResponse(BaseModel):
    variant_id: UUID
    service_id: UUID
    company_id: UUID
    name: str
    price: Decimal
    duration_min: int
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)


# ─── ServicePricingOverride ────────────────────────────────────────────────────

class PricingOverrideCreate(BaseModel):
    service_id: UUID
    price: Decimal
    duration_min: Optional[int] = None


class PricingOverrideUpdate(BaseModel):
    price: Optional[Decimal] = None
    duration_min: Optional[int] = None
    is_active: Optional[bool] = None


class PricingOverrideResponse(BaseModel):
    override_id: UUID
    professional_id: UUID
    service_id: UUID
    company_id: UUID
    price: Decimal
    duration_min: Optional[int] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)
