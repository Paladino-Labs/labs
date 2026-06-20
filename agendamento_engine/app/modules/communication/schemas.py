from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CommunicationSettingsResponse(BaseModel):
    settings_id: UUID
    company_id: UUID
    whatsapp_enabled: bool
    whatsapp_credential_id: UUID | None
    whatsapp_api_type: str
    email_enabled: bool
    smtp_credential_id: UUID | None
    quiet_hours_enabled: bool
    quiet_hours_start: Any
    quiet_hours_end: Any
    updated_at: Any

    model_config = {"from_attributes": True}


class CommunicationSettingsUpdate(BaseModel):
    whatsapp_enabled: bool | None = None
    whatsapp_credential_id: UUID | None = None
    whatsapp_api_type: str | None = None
    email_enabled: bool | None = None
    smtp_credential_id: UUID | None = None
    quiet_hours_enabled: bool | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class TemplateCreate(BaseModel):
    event_type: str
    channel: str
    audience: str
    body_template: str
    is_active: bool = True
    is_default: bool = False


class TemplateUpdate(BaseModel):
    body_template: str | None = None
    is_active: bool | None = None


class TemplateResponse(BaseModel):
    template_id: UUID
    company_id: UUID
    event_type: str
    channel: str
    audience: str
    body_template: str
    is_active: bool
    is_default: bool

    model_config = {"from_attributes": True}


class CommunicationLogResponse(BaseModel):
    log_id: UUID
    company_id: UUID
    template_id: UUID | None
    event_type: str
    channel: str
    recipient_id: UUID
    recipient_type: str
    recipient_name: str | None = None
    recipient_kind: str | None = None
    status: str
    scheduled_send_at: Any
    rendered_body: str | None
    sent_at: Any
    error_message: str | None
    created_at: Any

    model_config = {"from_attributes": True}
