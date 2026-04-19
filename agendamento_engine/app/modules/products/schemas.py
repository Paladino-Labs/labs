from uuid import UUID
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class ProductCreate(BaseModel):
    name: str
    price: Decimal
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: Optional[bool] = None


class ProductResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    price: Decimal
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: bool

    model_config = ConfigDict(from_attributes=True)
