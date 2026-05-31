from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SoftReservationCreate(BaseModel):
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    ttl_minutes: Optional[int] = None


class ReservationResponse(BaseModel):
    reservation_id: UUID
    company_id: UUID
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    type: str
    status: str
    appointment_id: Optional[UUID] = None
    expires_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class PromoteRequest(BaseModel):
    appointment_id: UUID


class FirmeDirectCreate(BaseModel):
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    appointment_id: UUID
    reason: str  # obrigatório: firme-direct é sempre um override manual


class DirectOccupancyCreate(BaseModel):
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    reason: str


class DirectOccupancyResponse(BaseModel):
    occupancy_id: UUID
    company_id: UUID
    professional_id: UUID
    start_at: datetime
    end_at: datetime
    appointment_id: Optional[UUID] = None
    reason: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opened_by: UUID

    class Config:
        from_attributes = True
