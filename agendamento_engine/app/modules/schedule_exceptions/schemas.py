from __future__ import annotations

from datetime import date, time
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ScheduleExceptionCreate(BaseModel):
    professional_id: UUID
    exception_date: date
    type: str  # SUBSTITUTIVE | ADDITIVE
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = None


class ScheduleExceptionResponse(BaseModel):
    exception_id: UUID
    company_id: UUID
    professional_id: UUID
    exception_date: date
    type: str
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: Optional[str] = None

    class Config:
        from_attributes = True
