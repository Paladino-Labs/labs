from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PackageCreate(BaseModel):
    name: str
    total_cotas: int = Field(..., gt=0)
    price: Decimal = Field(..., ge=0)
    service_id: Optional[UUID] = None
    validity_days: Optional[int] = None


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    total_cotas: Optional[int] = Field(None, gt=0)
    price: Optional[Decimal] = Field(None, ge=0)
    service_id: Optional[UUID] = None
    validity_days: Optional[int] = None
    is_active: Optional[bool] = None


class PackageResponse(BaseModel):
    package_id: UUID
    company_id: UUID
    name: str
    service_id: Optional[UUID]
    total_cotas: int
    price: Decimal
    validity_days: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class SellPackageRequest(BaseModel):
    customer_id: UUID
    seller_user_id: Optional[UUID] = None
    payment_method: str
    target_account_id: Optional[UUID] = None


class SellPackageResponse(BaseModel):
    purchase_id: UUID
    payment_id: Optional[UUID]


class PackagePurchaseResponse(BaseModel):
    purchase_id: UUID
    company_id: UUID
    customer_id: UUID
    package_id: UUID
    seller_user_id: Optional[UUID]
    payment_id: Optional[UUID]
    total_price: Decimal
    status: str
    activated_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True
