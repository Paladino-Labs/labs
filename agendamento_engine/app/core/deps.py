from uuid import UUID
from typing import Optional
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import User

# auto_error=False: sem token → credentials=None → levantamos 401 manualmente.
# O padrão (True) levantaria 403, que semanticamente significa "proibido" (autenticado
# mas sem permissão), não "não autenticado".
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = UUID(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Não autenticado")

    user = db.query(User).filter(User.id == user_id, User.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Não autenticado")

    return user


def get_current_company_id(user: User = Depends(get_current_user)) -> UUID:
    """Extrai o company_id do usuário autenticado. Usado como filtro multi-tenant."""
    return user.company_id


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Bloqueia acesso a rotas admin para usuários sem permissão."""
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user
