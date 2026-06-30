"""
Auth do Portal do Cliente — Sprint D.

JWT portal: claims DISTINTOS do JWT de tenant —
  {"sub": identity_id, "type": "portal", "iat": now, "exp": now + 24h}
SEM company_id: o cliente acessa dados de todos os seus tenants.
verify_portal_token rejeita JWT de tenant (type != "portal") → 401.

Magic link: token UUID4 cru no link, SHA-256 no banco (padrão do
manage_token do Sprint B), TTL 15min, single-use.

Envio de email: direto via Mailtrap HTTP / SMTP (mesmo padrão de
_send_reset_email_direct em auth/service.py) — a identity é global,
sem tenant, então CommunicationService.dispatch (que exige company_id)
não se aplica aqui.
"""
import hashlib
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.infrastructure.db.models import (
    PaladinoIdentity,
    PortalCredential,
    PortalMagicToken,
)

logger = logging.getLogger(__name__)

PORTAL_TOKEN_TYPE = "portal"
PORTAL_TOKEN_TTL_HOURS = 24
MAGIC_LINK_TTL_MINUTES = 15


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_portal_token(identity_id: UUID) -> str:
    """JWT portal: sub=identity_id, type="portal", sem company_id, 24h."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(identity_id),
        "type": PORTAL_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(hours=PORTAL_TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_portal_token(token: str) -> UUID:
    """Decodifica e valida claim type == "portal". Retorna identity_id.

    JWT de tenant (type ausente ou diferente) → 401.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Não autenticado")
    if payload.get("type") != PORTAL_TOKEN_TYPE:
        raise HTTPException(status_code=401, detail="Não autenticado")
    try:
        return UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Não autenticado")


# ── Hash de magic token (SHA-256 — padrão Sprint B) ──────────────────────────

def hash_magic_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Email direto (identidade global — sem tenant/CommunicationService) ───────

def _send_portal_email(recipient_email: str, subject: str, body: str) -> None:
    from app.core.config import settings as app_settings

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


def _magic_link_url(raw_token: str) -> str:
    base = (settings.FRONTEND_BASE_URL or settings.FRONTEND_URL).rstrip("/")
    return f"{base}/portal/magic/{raw_token}"


# ── Registro ──────────────────────────────────────────────────────────────────

def register(
    db: Session,
    email: str,
    name: str,
    phone: str,
    password: Optional[str] = None,
) -> dict:
    """
    Cria PortalCredential vinculada à PaladinoIdentity (via resolver — 422
    se telefone sem DDD). Se a identity já existia por telefone, o response
    sinaliza has_existing_history=True (adoção do histórico é a própria
    vinculação da credencial — confirmada pelo cliente no registro).
    Envia email de verificação (magic link marca email_verified).
    """
    from app.modules.identity.resolver import resolver

    email = email.strip().lower()
    existing = db.query(PortalCredential).filter(PortalCredential.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="E-mail já cadastrado no Portal")

    result = resolver.resolve(db, phone, name=name)

    cred_for_identity = (
        db.query(PortalCredential)
        .filter(PortalCredential.identity_id == result.identity_id)
        .first()
    )
    if cred_for_identity:
        raise HTTPException(
            status_code=409,
            detail="Já existe uma conta do Portal para este telefone",
        )

    identity = db.query(PaladinoIdentity).filter(
        PaladinoIdentity.id == result.identity_id
    ).first()
    if identity is not None:
        if name and not identity.name:
            identity.name = name
        if not identity.email:
            identity.email = email

    credential = PortalCredential(
        identity_id=result.identity_id,
        email=email,
        password_hash=hash_password(password) if password else None,
        email_verified=False,
    )
    db.add(credential)
    db.commit()

    # Religa customers órfãos (identity_id NULL) com este telefone em qualquer
    # tenant — garante que agendamentos legados apareçam no Portal.
    if identity is not None:
        _backfill_orphan_customers(db, identity)

    # Email de verificação — best-effort, não bloqueia o registro
    try:
        _issue_and_send_magic_link(
            db, result.identity_id, email,
            subject="Confirme seu e-mail — Portal Paladino",
            intro="Bem-vindo ao Portal Paladino! Confirme seu e-mail acessando o link:",
        )
    except Exception:
        logger.exception("portal register: falha ao enviar email de verificação para %s", email)

    return {
        "identity_id": str(result.identity_id),
        "has_existing_history": not result.is_new_identity,
        "message": "Conta criada. Verifique seu e-mail para confirmar o cadastro.",
    }


def _backfill_orphan_customers(db: Session, identity: PaladinoIdentity) -> None:
    """
    Após registro no portal, religa customers que têm o mesmo telefone mas
    identity_id = NULL (criados por caminhos legados). Opera cross-tenant por
    design — o portal é global.

    Matching: usa o MESMO algoritmo do scripts/backfill_identity.py
    (normalize_phone_e164) para casar variações com/sem o 9º dígito.
    NOTA: Customer.phone é armazenado SEM o '+' mas COM o DDI 55
    (ex.: "5562985657312"), enquanto identity.phone_national_normalized é
    "62985657312" (sem DDI). Por isso o filtro NÃO pode comparar diretamente
    com phone_national_normalized — normalizamos cada candidato e comparamos
    o E.164 canônico (identity.phone_e164). Pré-filtro por sufixo de 8 dígitos
    evita varredura total da tabela.
    """
    from fastapi import HTTPException as _HTTPException

    from app.infrastructure.db.models.customer import Customer
    from app.modules.identity.resolver import normalize_phone_e164

    canonical = identity.phone_e164  # "+5562985657312"
    last8 = (identity.phone_national_normalized or "")[-8:]
    if not last8:
        return

    candidates = (
        db.query(Customer)
        .filter(
            Customer.phone.like(f"%{last8}"),
            Customer.identity_id.is_(None),
            Customer.active == True,
        )
        .all()
    )

    linked = 0
    for customer in candidates:
        try:
            phone_e164, _ = normalize_phone_e164(customer.phone)
        except _HTTPException:
            continue  # telefone malformado — ignora (operador resolve)
        if phone_e164 == canonical:
            customer.identity_id = identity.id
            linked += 1

    if linked:
        db.commit()


# ── Login com senha ───────────────────────────────────────────────────────────

def login_with_password(db: Session, email: str, password: str) -> str:
    """Busca PortalCredential por email, verifica bcrypt, retorna JWT portal."""
    email = (email or "").strip().lower()
    credential = db.query(PortalCredential).filter(PortalCredential.email == email).first()
    if (
        not credential
        or not credential.password_hash
        or not verify_password(password, credential.password_hash)
    ):
        raise HTTPException(status_code=401, detail="E-mail ou senha inválidos")

    credential.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return create_portal_token(credential.identity_id)


# ── Magic link ────────────────────────────────────────────────────────────────

def _issue_and_send_magic_link(
    db: Session,
    identity_id: UUID,
    email: str,
    subject: str = "Seu link de acesso — Portal Paladino",
    intro: str = "Acesse o Portal Paladino pelo link abaixo:",
) -> None:
    raw_token = str(uuid_mod.uuid4())
    magic = PortalMagicToken(
        identity_id=identity_id,
        token_hash=hash_magic_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_TTL_MINUTES),
    )
    db.add(magic)
    db.commit()

    body = (
        f"{intro}\n\n"
        f"{_magic_link_url(raw_token)}\n\n"
        f"Válido por {MAGIC_LINK_TTL_MINUTES} minutos e de uso único.\n"
        "Se você não solicitou este acesso, ignore este e-mail."
    )
    _send_portal_email(email, subject, body)


def send_magic_link(db: Session, email: str) -> None:
    """
    Cria PortalMagicToken (15min) e envia por email. NUNCA revela se o
    email existe: retorna silenciosamente quando não encontrado (o router
    responde 200 sempre).
    """
    email = (email or "").strip().lower()
    credential = db.query(PortalCredential).filter(PortalCredential.email == email).first()
    if not credential:
        return  # silencioso — não revelar existência

    try:
        _issue_and_send_magic_link(db, credential.identity_id, email)
    except Exception:
        logger.exception("send_magic_link: falha ao enviar para %s", email)


def verify_magic_link(db: Session, token_raw: str) -> str:
    """
    Busca por hash, valida not used + not expired, marca used_at e
    email_verified, retorna JWT portal. Inválido/expirado/usado → 401.
    """
    token_hash = hash_magic_token(token_raw or "")
    magic = (
        db.query(PortalMagicToken)
        .filter(PortalMagicToken.token_hash == token_hash)
        .first()
    )
    now = datetime.now(timezone.utc)
    if not magic or magic.used_at is not None or magic.expires_at <= now:
        raise HTTPException(status_code=401, detail="Link inválido ou expirado")

    magic.used_at = now

    credential = (
        db.query(PortalCredential)
        .filter(PortalCredential.identity_id == magic.identity_id)
        .first()
    )
    if credential:
        credential.email_verified = True
        credential.last_login_at = now
    db.commit()

    return create_portal_token(magic.identity_id)
