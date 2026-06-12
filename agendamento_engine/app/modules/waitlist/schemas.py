from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WaitlistConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    enabled: bool
    priority_mode: str
    notification_window_hours: int


class WaitlistConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    priority_mode: Optional[str] = None
    notification_window_hours: Optional[int] = Field(None, ge=1)


class WaitlistEntryCreate(BaseModel):
    customer_id: UUID
    scope_type: str  # SERVICE | PROFESSIONAL | PRODUCT
    service_id: Optional[UUID] = None
    professional_id: Optional[UUID] = None
    product_id: Optional[UUID] = None


class WaitlistEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    customer_id: UUID
    scope_type: str
    service_id: Optional[UUID] = None
    professional_id: Optional[UUID] = None
    product_id: Optional[UUID] = None
    status: str
    priority: int
    source_channel: str
    notified_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
