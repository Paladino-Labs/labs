from typing import Any
from uuid import UUID

from pydantic import BaseModel, field_validator


VALID_PROVIDERS = {"WHATSAPP_EVOLUTION", "WHATSAPP_META", "SMTP", "ASAAS"}


class CredentialCreate(BaseModel):
    provider: str
    label: str | None = None
    secret: str
    config: dict[str, Any] | None = None

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in VALID_PROVIDERS:
            raise ValueError(f"provider deve ser um de: {', '.join(sorted(VALID_PROVIDERS))}")
        return v


class CredentialRotate(BaseModel):
    new_secret: str


class CredentialResponse(BaseModel):
    credential_id: UUID
    company_id: UUID
    provider: str
    label: str | None
    masked_preview: str | None
    config: dict[str, Any]
    status: str
    created_at: Any

    model_config = {"from_attributes": True}


class TestConnectionResponse(BaseModel):
    success: bool
    latency_ms: float | None = None
    error_message: str | None = None
