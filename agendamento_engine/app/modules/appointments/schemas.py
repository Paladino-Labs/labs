from uuid import UUID
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel


class ServiceRequest(BaseModel):
    service_id: UUID


class AppointmentCreate(BaseModel):
    professional_id: UUID
    client_id: UUID
    start_at: datetime
    services: List[ServiceRequest]
    idempotency_key: str


class AppointmentServiceSnapshot(BaseModel):
    id: UUID
    service_id: Optional[UUID]
    service_name: str
    duration_snapshot: Decimal
    price_snapshot: Decimal

    class Config:
        from_attributes = True


class ProfessionalSummary(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class CustomerSummary(BaseModel):
    id: UUID
    name: str
    phone: str

    class Config:
        from_attributes = True


class AppointmentResponse(BaseModel):
    id: UUID
    company_id: UUID
    professional_id: UUID
    client_id: UUID
    start_at: datetime
    end_at: datetime
    status: str
    financial_status: str
    subtotal_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    services: List[AppointmentServiceSnapshot]
    professional: Optional[ProfessionalSummary]
    customer: Optional[CustomerSummary]

    class Config:
        from_attributes = True


class RescheduleRequest(BaseModel):
    start_at: datetime


class CancelRequest(BaseModel):
    reason: Optional[str] = None
