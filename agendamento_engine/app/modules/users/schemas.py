from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

# Mantido para compatibilidade com o service legado (POST /users)
ALLOWED_ROLES = {"ADMIN", "PROFESSIONAL"}

# Papéis ativos atribuíveis no Estágio 0 (excluindo schema-only)
ACTIVE_ROLES = {"OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT", "PLATFORM_OWNER"}

# Papéis reservados — 422 se tentarem atribuir
SCHEMA_ONLY_ROLE_VALUES = {"PLATFORM_SUPPORT", "PLATFORM_BILLING", "PLATFORM_READONLY"}


class UserCreate(BaseModel):
    """Legado — criação direta com senha. Deprecado a partir do Sprint 2."""
    email: EmailStr
    password: str = Field(min_length=6)
    role: str = "PROFESSIONAL"


class UserResponse(BaseModel):
    id: UUID
    company_id: Optional[UUID] = None
    email: str
    name: Optional[str] = None
    role: str
    active: bool

    model_config = {"from_attributes": True}


class InviteUserRequest(BaseModel):
    email: EmailStr
    role: str
    name: Optional[str] = None
    professional_id: Optional[UUID] = None  # só relevante quando role=PROFESSIONAL


class InviteUserResponse(BaseModel):
    invitation_id: UUID
    expires_at: datetime


class AssignRoleRequest(BaseModel):
    role: str


class TransferOwnershipRequest(BaseModel):
    new_owner_user_id: UUID
    current_owner_new_role: str = "ADMIN"


class InvitationResponse(BaseModel):
    invitation_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime
    invited_by_user_id: UUID
    company_id: Optional[UUID] = None

    model_config = {"from_attributes": True}
