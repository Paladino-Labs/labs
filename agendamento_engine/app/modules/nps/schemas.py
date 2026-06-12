from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NpsConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    enabled: bool
    channel: str
    delay_minutes: int
    min_interval_days: int
    low_score_threshold: int
    low_score_alert_enabled: bool


class NpsConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    channel: Optional[str] = None
    delay_minutes: Optional[int] = Field(None, ge=0)
    min_interval_days: Optional[int] = Field(None, ge=0)
    low_score_threshold: Optional[int] = Field(None, ge=0, le=10)
    low_score_alert_enabled: Optional[bool] = None


class NpsResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    survey_id: UUID
    score: int
    comment: Optional[str] = None
    tenant_response: Optional[str] = None
    responded_at: Optional[datetime] = None


class NpsSurveyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    customer_id: UUID
    appointment_id: UUID
    status: str
    scheduled_for: datetime
    sent_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    expires_at: datetime


class NpsSurveyDetailResponse(NpsSurveyResponse):
    response: Optional[NpsResponseOut] = None


class PublicNpsRespondRequest(BaseModel):
    score: int = Field(..., ge=0, le=10)
    comment: Optional[str] = Field(None, max_length=2000)


class TenantResponseRequest(BaseModel):
    response: str = Field(..., min_length=1, max_length=2000)
