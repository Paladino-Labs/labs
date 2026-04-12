from uuid import UUID
from pydantic import BaseModel, EmailStr, Field

ALLOWED_ROLES = {"ADMIN", "PROFESSIONAL"}


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: str = "PROFESSIONAL"


class UserResponse(BaseModel):
    id: UUID
    company_id: UUID
    email: str
    role: str
    active: bool

    model_config = {"from_attributes": True}
