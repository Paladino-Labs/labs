from datetime import datetime
from decimal import Decimal
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class PackageItemCreate(BaseModel):
    item_type: Literal["SERVICE", "PRODUCT"]
    service_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    quantity: int = Field(..., gt=0)

    @model_validator(mode="after")
    def _validate_target(self) -> "PackageItemCreate":
        if self.item_type == "SERVICE":
            if self.service_id is None or self.product_id is not None:
                raise ValueError("item SERVICE exige service_id (e product_id nulo)")
        else:  # PRODUCT
            if self.product_id is None or self.service_id is not None:
                raise ValueError("item PRODUCT exige product_id (e service_id nulo)")
        return self


class PackageItemResponse(BaseModel):
    item_id: UUID
    item_type: str
    service_id: Optional[UUID] = None
    service_name: Optional[str] = None
    product_id: Optional[UUID] = None
    product_name: Optional[str] = None
    quantity: int
    display_order: int

    model_config = {"from_attributes": True}


class PackageCreate(BaseModel):
    name: str
    items: List[PackageItemCreate] = Field(..., min_length=1)
    price: Decimal = Field(..., ge=0)
    validity_days: Optional[int] = None


class PackageUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = Field(None, ge=0)
    validity_days: Optional[int] = None
    is_active: Optional[bool] = None


class PackageResponse(BaseModel):
    package_id: UUID
    company_id: UUID
    name: str
    items: List[PackageItemResponse]
    total_cotas: int
    price: Decimal
    validity_days: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


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
