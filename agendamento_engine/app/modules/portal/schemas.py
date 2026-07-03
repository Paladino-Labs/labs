from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, field_validator

from app.modules.identity.consent_service import ConsentType


class PortalRegisterRequest(BaseModel):
    email: EmailStr
    name: str
    phone: str
    password: Optional[str] = None

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        # Mesma regra do painel: mínimo 8 chars + 1 maiúscula + 1 número
        if len(v) < 8 or not any(c.isupper() for c in v) or not any(c.isdigit() for c in v):
            raise ValueError(
                "Senha deve ter no mínimo 8 caracteres, 1 maiúscula e 1 número"
            )
        return v


class PortalLoginRequest(BaseModel):
    email: EmailStr
    password: str


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkVerifyRequest(BaseModel):
    token: str


class PortalTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PortalConsentRequest(BaseModel):
    consent_type: str
    channel: Optional[str] = None      # WHATSAPP | EMAIL | SMS | None (todos)
    company_id: Optional[UUID] = None  # None = consent global Paladino-wide

    @field_validator("consent_type")
    @classmethod
    def consent_type_valid(cls, v: str) -> str:
        v = v.upper()
        if v not in ConsentType.ALL:
            raise ValueError(
                f"consent_type inválido — use um de: {', '.join(ConsentType.ALL)}"
            )
        return v


class PaymentSourceCreateRequest(BaseModel):
    company_id: UUID
    source_token: str
    mode: str                          # ALWAYS | ONCE
    last_four: Optional[str] = None
    brand: Optional[str] = None


class PortalProfileUpdateRequest(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None


class PortalRescheduleRequest(BaseModel):
    start_at: datetime


class CreditConsumptionOut(BaseModel):
    occurred_at: datetime
    appointment_id: Optional[UUID] = None
    service_name: Optional[str] = None
    professional_name: Optional[str] = None
    quantity_used: int = 1
