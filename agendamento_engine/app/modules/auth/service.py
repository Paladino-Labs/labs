from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password, create_access_token
from app.infrastructure.db.models import User


def authenticate(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email, User.active == True).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id),
        "role": user.role,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "company_id": str(user.company_id),
        "role": user.role,
    }
