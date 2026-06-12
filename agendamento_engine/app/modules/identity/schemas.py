from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.modules.identity.consent_service import ConsentType


class ConsentRecordResponse(BaseModel):
    id: UUID
    identity_id: UUID
    company_id: Optional[UUID] = None
    consent_type: str
    channel: Optional[str] = None
    status: str
    source_channel: str
    occurred_at: datetime
    notes: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ConsentChangeRequest(BaseModel):
    consent_type: str
    channel: Optional[str] = None      # WHATSAPP | EMAIL | SMS | None (todos)
    notes: Optional[str] = None

    @field_validator("consent_type")
    @classmethod
    def consent_type_valid(cls, v: str) -> str:
        v = v.upper()
        if v not in ConsentType.ALL:
            raise ValueError(
                f"consent_type inválido — use um de: {', '.join(ConsentType.ALL)}"
            )
        return v


class IdentityResponse(BaseModel):
    """
    Dados da identity expostos em API. CPF SEMPRE masked — cpf_encrypted
    e cpf_hash nunca saem em resposta (padrão PII do Sprint 8).
    """
    id: UUID
    phone_e164: str
    phone_national_normalized: str
    name: Optional[str] = None
    email: Optional[str] = None
    cpf_masked: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)
