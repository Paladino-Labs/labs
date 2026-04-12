# app/api/schemas/client_schema.py

from pydantic import BaseModel
from uuid import UUID


class ClientCreate(BaseModel):
    name: str
    phone: str


class ClientOut(BaseModel):
    id: UUID
    name: str
    phone: str

    class Config:
        from_attributes = True