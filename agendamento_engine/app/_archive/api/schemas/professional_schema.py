from uuid import UUID

from pydantic import BaseModel, EmailStr


class ProfessionalCreate(BaseModel):
    name: str
    email: EmailStr | None = None
    service_ids: list[UUID] = []


class ProfessionalUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None


class ProfessionalOut(BaseModel):
    id: UUID
    name: str
    email: str | None = None
    active: bool | None = None

    class Config:
        from_attributes = True


class ProfessionalServiceLinkRequest(BaseModel):
    service_ids: list[UUID]


class ProfessionalServiceOut(BaseModel):
    id: UUID
    name: str
    price: float
    duration: int
    active: bool | None = None

    class Config:
        from_attributes = True
