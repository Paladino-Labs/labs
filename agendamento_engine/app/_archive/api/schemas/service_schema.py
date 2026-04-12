from uuid import UUID

from pydantic import BaseModel


class ServiceCreate(BaseModel):
    name: str
    price: float
    duration: int


class ServiceUpdate(BaseModel):
    name: str | None = None
    price: float | None = None
    duration: int | None = None
    active: bool | None = None


class ServiceOut(BaseModel):
    id: UUID
    name: str
    price: float
    duration: int
    active: bool | None = None

    class Config:
        from_attributes = True
