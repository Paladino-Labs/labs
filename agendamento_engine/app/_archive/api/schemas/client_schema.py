from uuid import UUID

from pydantic import BaseModel


class ClientCreate(BaseModel):
    name: str
    phone: str
    email: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: str | None = None


class ClientOut(BaseModel):
    id: UUID
    name: str
    phone: str
    email: str | None = None

    class Config:
        from_attributes = True
