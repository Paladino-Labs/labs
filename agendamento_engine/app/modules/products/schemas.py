from uuid import UUID
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, field_validator


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
    stock: Optional[int] = None

    @field_validator("stock")
    @classmethod
    def stock_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v < 0:
            raise ValueError("stock não pode ser negativo")
        return v


class ProductResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    price: Decimal
    description: Optional[str] = None
    image_url: Optional[str] = None
    active: bool
    stock: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)
