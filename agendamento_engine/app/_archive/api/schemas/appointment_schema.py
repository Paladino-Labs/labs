from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ServiceRequest(BaseModel):
    service_id: UUID


class AppointmentCreate(BaseModel):
    professional_id: UUID
    client_id: UUID
    start_at: datetime
    services: List[ServiceRequest]
    coupon_code: Optional[str] = Field(None, max_length=20)
    idempotency_key: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    email: str
    password: str


class RescheduleSchema(BaseModel):
    start_at: datetime


class CancelSchema(BaseModel):
    reason: Optional[str] = None
