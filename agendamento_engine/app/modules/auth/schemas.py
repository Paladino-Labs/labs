import re
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

_STRONG_PASSWORD_RE = re.compile(r'^(?=.*[A-Z])(?=.*\d).{8,}$')


def _validate_strong_password(v: str) -> str:
    if not _STRONG_PASSWORD_RE.match(v):
        raise ValueError(
            "A senha deve ter mínimo 8 caracteres, 1 letra maiúscula e 1 número."
        )
    return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    company_id: Optional[str] = None
    role: str


class ActivateRequest(BaseModel):
    token: UUID
    password: str = Field(min_length=6)
    password_confirm: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_strong_password(v)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str
    new_password_confirm: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        return _validate_strong_password(v)


class MessageResponse(BaseModel):
    message: str
