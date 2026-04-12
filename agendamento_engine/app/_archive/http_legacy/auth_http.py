from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.auth.schemas import CurrentUserResponse, LoginRequest, TokenResponse
from app.modules.auth.service import authenticate_user, build_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, data.email, data.password)
    return {"access_token": build_access_token(user), "token_type": "bearer"}


@router.get("/me", response_model=CurrentUserResponse)
def me(current_user=Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "tenant_id": current_user.company_id,
        "is_admin": current_user.is_admin,
    }
