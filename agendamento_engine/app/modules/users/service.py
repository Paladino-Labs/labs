from typing import List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.infrastructure.db.models.user import User
from app.modules.users.schemas import UserCreate, ALLOWED_ROLES


def list_users(db: Session, company_id: UUID) -> List[User]:
    return (
        db.query(User)
        .filter(User.company_id == company_id)
        .order_by(User.email)
        .all()
    )


def create_user(db: Session, company_id: UUID, data: UserCreate) -> User:
    if data.role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Role inválida: '{data.role}'. Permitidas: {sorted(ALLOWED_ROLES)}",
        )

    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"E-mail '{data.email}' já está em uso",
        )

    user = User(
        company_id=company_id,
        email=data.email,
        password_hash=hash_password(data.password),
        role=data.role,
        active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
