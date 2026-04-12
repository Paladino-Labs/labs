from uuid import UUID

from pydantic import BaseModel, EmailStr


class CompanyOut(BaseModel):
    id: UUID
    name: str

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    is_admin: bool = False


class UserOut(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    email: str
    is_admin: bool
    active: bool

    class Config:
        from_attributes = True
