from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_user
from app.core.rate_limit import limiter
from app.infrastructure.db.models import User
from app.modules.auth import schemas, service
from app.modules.auth.activate_service import activate_account

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=schemas.TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: schemas.LoginRequest, db: Session = Depends(get_db)):
    return service.authenticate(db, body.email, body.password)


@router.post("/activate", response_model=schemas.TokenResponse)
def activate(body: schemas.ActivateRequest, db: Session = Depends(get_db)):
    """Ativação de conta via token de convite. Endpoint público (sem autenticação)."""
    return activate_account(db, body.token, body.password, body.password_confirm, body.name)


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    }


@router.post("/forgot-password", response_model=schemas.MessageResponse)
def forgot_password(body: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Inicia fluxo de recuperação de senha. Retorna 200 independente de o e-mail existir."""
    service.forgot_password(db, body.email)
    return {"message": "Se o e-mail estiver cadastrado, você receberá o código em breve."}


@router.post("/reset-password", response_model=schemas.MessageResponse)
def reset_password(body: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    """Redefine a senha usando o token de 6 dígitos recebido."""
    service.reset_password(db, body.token, body.new_password, body.new_password_confirm)
    return {"message": "Senha redefinida com sucesso."}


@router.post("/change-password", response_model=schemas.MessageResponse)
def change_password(
    body: schemas.ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Altera a senha do usuário autenticado."""
    service.change_password(
        db, user, body.current_password, body.new_password, body.new_password_confirm
    )
    return {"message": "Senha alterada com sucesso."}


@router.patch("/profile")
def update_profile(
    body: schemas.UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Atualiza o perfil do usuário autenticado (qualquer role).

    Apenas campos de perfil pessoal — email, role e company_id são imutáveis aqui.
    Se name=None no body, o campo é limpo (nullable aceito).
    Se name não for enviado ({}) o nome existente é preservado.
    """
    if body.name is not None:
        user.name = body.name
        db.commit()
        db.refresh(user)
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    }
