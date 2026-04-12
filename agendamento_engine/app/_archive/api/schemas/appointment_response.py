from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from typing import List


class ClientOut(BaseModel):
    id: UUID
    name: str


class ProfessionalOut(BaseModel):
    id: UUID
    name: str


class ServiceSnapshotOut(BaseModel):
    service_name: str
    price_snapshot: float
    duration_snapshot: int

    class Config:
        from_attributes = True

class AppointmentListItem(BaseModel):
    id: UUID
    start_at: datetime
    end_at: datetime
    status: str

    client: ClientOut | None
    professional: ProfessionalOut | None
    services: List[ServiceSnapshotOut]

    class Config:
        from_attributes = True