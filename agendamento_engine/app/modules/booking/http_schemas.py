"""
Schemas HTTP do router público de booking.

Separados dos dataclasses internos de booking/schemas.py — estes são os
contratos de entrada e saída da API REST, com validação Pydantic e
serialização automática pelo FastAPI.

Convenção de nomes:
  *Request  — body de entrada (POST/PATCH)
  *Response — body de saída
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ─── Saída: /info ─────────────────────────────────────────────────────────────

class CompanyInfoResponse(BaseModel):
    company_name: str
    active: bool
    online_booking_enabled: bool
    services_count: int


# ─── Saída: /services ─────────────────────────────────────────────────────────

class ServiceOptionResponse(BaseModel):
    id: UUID
    name: str
    price: Decimal
    duration_minutes: int
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /professionals ────────────────────────────────────────────────────

class ProfessionalOptionResponse(BaseModel):
    id: Optional[UUID]      # None = "Qualquer disponível"
    name: str
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /dates ────────────────────────────────────────────────────────────

class DateOptionResponse(BaseModel):
    date: date
    label: str
    has_availability: bool
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /slots ────────────────────────────────────────────────────────────

class SlotOptionResponse(BaseModel):
    start_at: datetime
    end_at: datetime
    professional_id: UUID
    professional_name: str
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Entrada: POST /confirm ───────────────────────────────────────────────────

class ConfirmBookingRequest(BaseModel):
    service_id: UUID
    professional_id: UUID           # deve ser UUID concreto; "any" resolvido pelo frontend
    start_at: datetime
    customer_phone: str             # usado para identificar/criar o cliente
    customer_name: str
    idempotency_key: str


# ─── Saída: POST /confirm ─────────────────────────────────────────────────────

class BookingResultResponse(BaseModel):
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: GET /appointments ─────────────────────────────────────────────────

class AppointmentSummaryResponse(BaseModel):
    id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


# ─── Entrada: PATCH /appointments/{id}/cancel ────────────────────────────────

class CancelBookingRequest(BaseModel):
    reason: Optional[str] = None
    phone: str                      # identifica o cliente para autorização


# ─── Saída: PATCH /appointments/{id}/cancel ──────────────────────────────────

class CancelResultResponse(BaseModel):
    success: bool
    message: str