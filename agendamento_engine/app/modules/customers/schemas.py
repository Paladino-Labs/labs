from uuid import UUID
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: Optional[EmailStr] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    notes: Optional[str] = None
    active: Optional[bool] = None


class CustomerResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    phone: str
    email: Optional[str] = None
    notes: Optional[str] = None
    active: bool

    model_config = ConfigDict(from_attributes=True)


class CustomerAppointmentItem(BaseModel):
    """Resumo de um agendamento para exibição no histórico do cliente."""
    id: UUID
    start_at: str          # ISO 8601
    end_at: str
    status: str
    service_names: list[str]
    professional_name: Optional[str] = None
    total_amount: str
