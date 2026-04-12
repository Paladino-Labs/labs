from uuid import UUID
from typing import Optional
from pydantic import BaseModel, EmailStr


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    active: Optional[bool] = None


class CustomerResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    phone: str
    email: Optional[str]
    active: bool

    class Config:
        from_attributes = True
