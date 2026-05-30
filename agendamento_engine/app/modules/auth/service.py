import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password, hash_password, create_access_token
from app.infrastructure.db.models import User
from app.infrastructure.db.models.password_reset_token import PasswordResetToken


def authenticate(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email, User.active == True).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    token = create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": str(user.id),
        "company_id": str(user.company_id) if user.company_id else None,
        "role": user.role,
    }


def forgot_password(db: Session, email: str) -> None:
    """Gera token de 6 dígitos, grava hash e envia via CommunicationService.

    Retorna sem erro independente de o email existir ou não (não revelar existência).
    """
    user = db.query(User).filter(User.email == email, User.active == True).first()
    if not user:
        return  # silencioso

    # Gera token numérico de 6 dígitos
    raw_token = "".join(random.choices(string.digits, k=6))
    token_hash = hash_password(raw_token)  # bcrypt rounds=12 via pwd_context

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    # Invalida tokens anteriores não utilizados do mesmo usuário
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,
    ).update({"used": True})

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()

    # Envia via CommunicationService quando disponível.
    # Falha de envio não deve bloquear a resposta ao usuário.
    try:
        from app.modules.communication.service import communication_service
        communication_service.dispatch(
            event_type="auth.password_reset_requested",
            company_id=user.company_id,
            context={
                "recipient_phone": None,
                "reset_token": raw_token,
                "user_name": user.name,
                "email": user.email,
            },
            recipient_id=user.id,
            recipient_type="USER",
            db=db,
        )
    except Exception:
        pass  # best-effort; token já gravado


def reset_password(
    db: Session,
    raw_token: str,
    new_password: str,
    new_password_confirm: str,
) -> None:
    """Valida token, atualiza senha e marca token como usado."""
    if new_password != new_password_confirm:
        raise HTTPException(status_code=422, detail="As senhas não coincidem.")

    now = datetime.now(timezone.utc)

    # Busca tokens válidos e não expirados — verifica cada um (pode haver apenas 1 ativo por usuário)
    candidates = (
        db.query(PasswordResetToken)
        .filter(
            PasswordResetToken.used == False,
            PasswordResetToken.expires_at > now,
        )
        .all()
    )

    matched: PasswordResetToken | None = None
    for candidate in candidates:
        if verify_password(raw_token, candidate.token_hash):
            matched = candidate
            break

    if not matched:
        raise HTTPException(
            status_code=400,
            detail="Token inválido, expirado ou já utilizado.",
        )

    # Marca como usado imediatamente (antes do commit da senha para evitar race condition)
    matched.used = True
    db.flush()

    user = db.query(User).filter(User.id == matched.user_id, User.active == True).first()
    if not user:
        raise HTTPException(status_code=400, detail="Usuário não encontrado ou inativo.")

    user.password_hash = hash_password(new_password)
    db.commit()


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    new_password_confirm: str,
) -> None:
    """Valida senha atual e atualiza para nova senha."""
    if new_password != new_password_confirm:
        raise HTTPException(status_code=422, detail="As senhas não coincidem.")

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    user.password_hash = hash_password(new_password)
    db.commit()
