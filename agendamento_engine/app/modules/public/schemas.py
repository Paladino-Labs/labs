"""
Schemas públicos — usados pelos endpoints /public/{slug}/*.

Não expõem company_id nem campos internos.
Todos os campos monetários são strings para evitar problemas de serialização decimal.
"""
from datetime import datetime, date
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, field_validator


# ─── Company info ─────────────────────────────────────────────────────────────

class CompanyPublicInfo(BaseModel):
    name: str
    slug: str
    online_booking_enabled: bool


# ─── Catalog ──────────────────────────────────────────────────────────────────

class ServicePublicInfo(BaseModel):
    id: UUID
    name: str
    price: str                  # "50.00"
    duration_minutes: int
    description: Optional[str] = None
    image_url: Optional[str] = None


class ProfessionalPublicInfo(BaseModel):
    id: Optional[UUID] = None   # None = "Qualquer disponível"
    name: str


# ─── Slots ────────────────────────────────────────────────────────────────────

class SlotPublicInfo(BaseModel):
    start_at: datetime
    end_at: datetime
    professional_id: UUID
    professional_name: str


# ─── Booking request / response ───────────────────────────────────────────────

class PublicBookRequest(BaseModel):
    service_id: UUID
    professional_id: UUID       # deve ser um UUID real (frontend resolve "any")
    start_at: datetime
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None

    @field_validator("customer_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nome deve ter pelo menos 2 caracteres")
        return v

    @field_validator("customer_phone")
    @classmethod
    def phone_not_empty(cls, v: str) -> str:
        import re
        digits = re.sub(r"\D", "", v)
        if len(digits) < 10:
            raise ValueError("Telefone inválido")
        return v


class PublicBookResponse(BaseModel):
    token: str                  # WebBookingSession.token — para URL /book/confirm/{token}
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    end_at: datetime
    total_amount: str
