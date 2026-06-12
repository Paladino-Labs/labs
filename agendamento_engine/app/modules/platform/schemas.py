from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class TenantStatusUpdate(BaseModel):
    status: str  # TRIAL | ACTIVE | SUSPENDED | CHURNED
    reason: Optional[str] = None


class ImpersonationGrantCreate(BaseModel):
    company_id: UUID
    mode: str = "READ_ONLY"  # READ_ONLY | ELEVATED
    reason: str
    duration_minutes: int = 30


class FlagUpdate(BaseModel):
    value: Any


class SettingUpdate(BaseModel):
    value: Any


class RedispatchRequest(BaseModel):
    reason: str
