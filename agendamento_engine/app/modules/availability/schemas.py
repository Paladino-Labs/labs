from uuid import UUID
from datetime import datetime, date
from typing import List
from pydantic import BaseModel


class AvailableSlot(BaseModel):
    start_at: datetime
    end_at: datetime
    professional_id: UUID
    professional_name: str


class AvailabilityQuery(BaseModel):
    professional_id: UUID
    service_id: UUID
    date: date
