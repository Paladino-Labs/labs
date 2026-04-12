from uuid import UUID
from typing import Optional
from decimal import Decimal
from pydantic import BaseModel, ConfigDict


class ServiceCreate(BaseModel):
    name: str
    price: Decimal
    duration: int  # minutos


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    duration: Optional[int] = None
    active: Optional[bool] = None


class ServiceResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    price: Decimal
    duration: int
    active: bool

    model_config = ConfigDict(from_attributes=True)
