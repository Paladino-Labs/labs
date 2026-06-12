import logging
import random
import string
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import verify_password, hash_password, create_access_token
from app.infrastructure.db.models import User
from app.infrastructure.db.models.password_reset_token import PasswordResetToken

logger = logging.getLogger(__name__)


def _send_reset_email_direct(recipient_email: str, user_name: str, token: str) -> None:
    """Envia email de reset diretamente via Mailtrap/SMTP, sem passar pelo CommunicationService.

    Usado para PLATFORM_OWNER (company_id=None) que não tem tenant nem CommunicationSetting.
    """
    from app.core.config import settings as app_settings

    subject = "Seu código de redefinição de senha — Paladino"
    body = (
        f"Olá, {user_name}!\n\n"
        f"Seu código de redefinição de senha é: {token}\n\n"
        "Válido por 15 minutos. Não compartilhe este código.\n\n"
        "Se você não solicitou a redefinição, ignore este e-mail."
    )
    from_email = app_settings.SMTP_FROM_EMAIL or "noreply@paladino.app"

    if app_settings.MAILTRAP_API_TOKEN:
        import requests
        if app_settings.MAILTRAP_SANDBOX_INBOX_ID:
            url = f"https://sandbox.api.mailtrap.io/api/send/{app_settings.MAILTRAP_SANDBOX_INBOX_ID}"
            headers = {"Api-Token": app_settings.MAILTRAP_API_TOKEN}
        else:
            url = "https://send.api.mailtrap.io/api/send"
            headers = {"Authorization": f"Bearer {app_settings.MAILTRAP_API_TOKEN}"}
        payload = {
            "from": {"email": from_email, "name": "Paladino"},
            "to": [{"email": recipient_email}],
            "subject": subject,
            "text": body,
        }
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if not resp.ok:
            raise RuntimeError(f"Mailtrap erro {resp.status_code}: {resp.text}")
        return

    # Fallback SMTP
    import smtplib
    from email.mime.text import MIMEText
    if not app_settings.SMTP_HOST:
        raise RuntimeError("Email não configurado: MAILTRAP_API_TOKEN e SMTP_HOST ausentes")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = recipient_email
    with smtplib.SMTP(app_settings.SMTP_HOST, app_settings.SMTP_PORT, timeout=10) as s:
        if app_settings.SMTP_USE_TLS:
            s.starttls()
        if app_settings.SMTP_USER and app_settings.SMTP_PASSWORD:
            s.login(app_settings.SMTP_USER, app_settings.SMTP_PASSWORD)
        s.sendmail(from_email, [recipient_email], msg.as_string())


def authenticate(db: Session, email: str, password: str) -> dict:
    user = db.query(User).filter(User.email == email, User.active == True).first()

    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    # Sprint C: tenant SUSPENDED bloqueia login de todos os seus usuários.
    # PLATFORM_OWNER (company_id=None) nunca passa por este check.
    if user.company_id is not None:
        from app.infrastructure.db.models import Company

        company = db.query(Company).filter(Company.id == user.company_id).first()
        if company is not None and company.status == "SUSPENDED":
            raise HTTPException(
                status_code=403,
                detail="Tenant suspenso. Entre em contato com o suporte.",
            )

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

    # Envia via CommunicationService (tenant) ou direto (PLATFORM_OWNER sem company).
    # Falha de envio não deve bloquear a resposta ao usuário.
    try:
        display_name = user.name or user.email.split("@")[0]
        if user.company_id is None:
            # PLATFORM_OWNER: sem tenant, sem CommunicationSetting — envia diretamente.
            _send_reset_email_direct(user.email, display_name, raw_token)
        else:
            from app.modules.communication.service import communication_service
            communication_service.dispatch(
                event_type="auth.password_reset_requested",
                company_id=user.company_id,
                context={
                    "recipient_phone": getattr(user, "phone", None),
                    "recipient_email": user.email,
                    "email_subject": "Seu código de redefinição de senha — Paladino",
                    "token": raw_token,
                    "user_name": display_name,
                    "email": user.email,
                },
                recipient_id=user.id,
                recipient_type="CLIENT",
                db=db,
            )
    except Exception:
        logger.exception("forgot_password: falha ao enviar email para %s", email)


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
    user.last_password_change_at = now
    db.commit()


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    new_password_confirm: str,
) -> None:
    """Valida senha atual e atualiza para nova senha.

    Atualiza last_password_change_at para que tokens emitidos antes desta
    data sejam invalidados por get_current_user.
    """
    if new_password != new_password_confirm:
        raise HTTPException(status_code=422, detail="As senhas não coincidem.")

    if not verify_password(current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")

    user.password_hash = hash_password(new_password)
    user.last_password_change_at = datetime.now(timezone.utc)
    db.commit()
