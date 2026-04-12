from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.models import Company, User


def get_company_or_404(db: Session, company_id):
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")
    return company


def list_company_users(db: Session, company_id):
    return db.query(User).filter(User.company_id == company_id).order_by(User.email.asc()).all()


def create_company_user(db: Session, company_id, email: str, password: str, is_admin: bool):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Usuário já cadastrado")

    user = User(
        company_id=company_id,
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
        active=True,
    )

    db.add(user)
    db.commit()
    db.refresh(user)
    return user
