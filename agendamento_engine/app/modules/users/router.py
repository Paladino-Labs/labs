from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import require_admin
from app.infrastructure.db.models.user import User
from app.modules.users import schemas, service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/", response_model=List[schemas.UserResponse])
def list_users(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Lista todos os usuários da empresa. Restrito a admins."""
    return service.list_users(db, admin.company_id)


@router.post("/", response_model=schemas.UserResponse, status_code=201)
def create_user(
    body: schemas.UserCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Cria um novo usuário ADMIN ou PROFESSIONAL na empresa do admin autenticado."""
    return service.create_user(db, admin.company_id, body)
