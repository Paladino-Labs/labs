"""Serviço de ativação de conta via token de convite."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password, create_access_token
from app.infrastructure.db.models.user import User
from app.infrastructure.db.models.user_invitation import UserInvitation


def activate_account(
    db: Session,
    token: UUID,
    password: str,
    password_confirm: str,
    name: Optional[str] = None,
) -> dict:
    if password != password_confirm:
        raise HTTPException(status_code=422, detail="As senhas não coincidem.")

    # Comparar como string é compatível com PostgreSQL (UUID aceita string) e SQLite
    token_str = str(token)
    invitation = (
        db.query(UserInvitation)
        .filter(UserInvitation.token == token_str)
        .first()
    )

    if not invitation:
        raise HTTPException(status_code=410, detail="Token inválido ou já utilizado.")

    if invitation.status != "PENDING":
        # Já aceito, expirado ou cancelado
        raise HTTPException(status_code=410, detail="Token inválido ou já utilizado.")

    # Normalize para aware — SQLite armazena sem timezone; PostgreSQL armazena com.
    exp = invitation.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        invitation.status = "EXPIRED"
        db.commit()
        raise HTTPException(status_code=410, detail="Token expirado.")

    # Verificar se email já existe (idempotência: não criar duplicata)
    existing = db.query(User).filter(User.email == invitation.email).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"E-mail '{invitation.email}' já está em uso.",
        )

    user = User(
        id=str(uuid.uuid4()),
        company_id=str(invitation.company_id) if invitation.company_id else None,
        email=invitation.email,
        password_hash=hash_password(password),
        role=invitation.role,
        active=True,
        name=name,
    )
    db.add(user)

    # Invalidar token imediatamente
    invitation.status = "ACCEPTED"

    db.commit()
    db.refresh(user)

    token_data = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    })

    return {
        "access_token": token_data,
        "token_type": "bearer",
        "user_id": str(user.id),
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    }
