from uuid import UUID
from datetime import time, datetime
from typing import Optional, List
from pydantic import BaseModel


class WorkingHourCreate(BaseModel):
    professional_id: UUID
    weekday: int          # 0 = segunda … 6 = domingo
    opening_time: time
    closing_time: time
    is_active: bool = True


class WorkingHourResponse(BaseModel):
    id: UUID
    company_id: UUID
    professional_id: UUID
    weekday: int
    opening_time: time
    closing_time: time
    is_active: bool

    class Config:
        from_attributes = True


class ScheduleBlockCreate(BaseModel):
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    reason: Optional[str] = None


class ScheduleBlockResponse(BaseModel):
    id: UUID
    company_id: UUID
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    reason: Optional[str]

    class Config:
        from_attributes = True
