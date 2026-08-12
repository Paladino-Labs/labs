import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from app.core.security import hash_password
from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.infrastructure.db.models.user import User, INVITE_PERMISSION
from app.infrastructure.db.models.user_invitation import UserInvitation
from app.modules.users.schemas import (
    UserCreate,
    ALLOWED_ROLES,
    ACTIVE_ROLES,
    SCHEMA_ONLY_ROLE_VALUES,
)


# ── helpers de validação ────────────────────────────────────────────────────

def _assert_not_schema_only(role: str) -> None:
    if role in SCHEMA_ONLY_ROLE_VALUES:
        raise HTTPException(
            status_code=422,
            detail="Este papel está reservado para uso futuro e não pode ser atribuído.",
        )


def _assert_not_platform_owner_by_tenant(actor: User, target_role: str) -> None:
    """PLATFORM_OWNER só pode ser atribuído por outro PLATFORM_OWNER."""
    if target_role == "PLATFORM_OWNER" and actor.role != "PLATFORM_OWNER":
        raise HTTPException(
            status_code=403,
            detail="PLATFORM_OWNER só pode ser atribuído por outro PLATFORM_OWNER.",
        )


def _assert_can_invite(actor: User, target_role: str) -> None:
    allowed = INVITE_PERMISSION.get(actor.role, set())
    if target_role not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Papel '{actor.role}' não pode convidar para o papel '{target_role}'.",
        )


def _count_active_owners(db: Session, company_id: UUID) -> int:
    return (
        db.query(User)
        .filter(
            User.company_id == company_id,
            User.role == "OWNER",
            User.active == True,
        )
        .count()
    )


# ── list ────────────────────────────────────────────────────────────────────

def list_users(db: Session, company_id: UUID) -> List[User]:
    return (
        db.query(User)
        .filter(User.company_id == company_id)
        .order_by(User.email)
        .all()
    )


# ── legado (deprecado) ───────────────────────────────────────────────────────

def create_user(db: Session, company_id: UUID, data: UserCreate) -> User:
    """Legado — cria usuário diretamente com senha. Deprecado; usar invite."""
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


# ── convite ──────────────────────────────────────────────────────────────────

def _normalize_invite_phone(raw_phone: str) -> str:
    """Telefone do convite → E.164 sem o '+', pronto para o `evolution_client`.

    Duas etapas, o mesmo idioma dos 4 formulários públicos (A5 §3.1 classifica a
    separação como legítima):

      1. `validate_user_phone_input` — GATE de formulário: whitelist ANATEL de
         DDD, rejeita DDI, mensagem de erro legível para quem está digitando.
      2. `normalize_phone_e164` — a normalização CANÔNICA-ESTRITA: insere o 9º
         dígito de celular e produz o E.164.

    ⚠️ Existem 4 normalizações de telefone no backend. A quarta
    (`public/service._normalize_phone`) NÃO insere o 9º dígito e produziria uma
    chave diferente para o mesmo número — não usar.
    """
    from app.modules.identity.resolver import (
        InvalidUserPhoneError,
        normalize_phone_e164,
        validate_user_phone_input,
    )

    if not (raw_phone or "").strip():
        raise HTTPException(
            status_code=422,
            detail="Telefone é obrigatório no convite — é por ele que a pessoa "
                   "recebe o acesso.",
        )

    try:
        validate_user_phone_input(raw_phone)
    except InvalidUserPhoneError as exc:
        raise HTTPException(status_code=422, detail=exc.message)

    phone_e164, _national = normalize_phone_e164(raw_phone)
    # Convenção do repositório: armazenado sem o '+' (idem customers.phone)
    return phone_e164.lstrip("+")


def invite_user(
    db: Session,
    actor: User,
    email: str,
    role: str,
    request_ip: Optional[str] = None,
    request_ua: Optional[str] = None,
    name: Optional[str] = None,
    professional_id: Optional[UUID] = None,
    phone: Optional[str] = None,
) -> UserInvitation:
    _assert_not_schema_only(role)
    _assert_not_platform_owner_by_tenant(actor, role)
    _assert_can_invite(actor, role)

    normalized_phone = _normalize_invite_phone(phone or "")

    # Actor não pode elevar o próprio papel via convite (convite cria usuário novo,
    # mas a verificação de autoelevação aplica-se a assign_role)

    def _s(v):
        return str(v) if v is not None else None

    invitation = UserInvitation(
        invitation_id=_s(uuid.uuid4()),
        company_id=_s(actor.company_id),  # NULL para PLATFORM_OWNER
        email=email,
        phone=normalized_phone,
        role=role,
        token=_s(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        status="PENDING",
        invited_by_user_id=_s(actor.id),
        professional_id=_s(professional_id),  # pode ser None
    )
    db.add(invitation)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role=actor.role,
            action="invite_user",
            resource_type="UserInvitation",
            resource_id=invitation.invitation_id,
            company_id=actor.company_id,
            after_snapshot={"email": email, "role": role},
            ip_address=request_ip,
            user_agent=request_ua,
        ),
        db,
    )
    db.commit()
    db.refresh(invitation)

    # Envia o convite (best-effort — falha não bloqueia a resposta).
    try:
        from app.core.config import settings as app_settings
        from app.modules.communication.service import communication_service
        from app.infrastructure.db.models.company import Company

        company = db.query(Company).filter(
            Company.id == actor.company_id
        ).first()
        company_name = company.name if company else "Paladino"

        activation_link = (
            f"{app_settings.FRONTEND_URL}/activate?token={invitation.token}"
        )

        # Convites sempre usam audience="CLIENT" — o convidado ainda não é
        # um usuário do sistema e um único template cobre todos os roles.
        #
        # `recipient_phone` é o telefone DO CONVIDADO — nunca o do dono da
        # empresa. Sem essa distinção o link de ativação da conta de um
        # OPERATOR iria para o WhatsApp do OWNER (tomada de conta).
        communication_service.dispatch(
            event_type="user.invitation_sent",
            company_id=actor.company_id,
            context={
                "recipient_phone": normalized_phone,
                "recipient_email": email,
                "email_subject": f"Você foi convidado para {company_name} — Paladino",
                "activation_link": activation_link,
                "invitation_token": invitation.token,
                "company_name": company_name,
                "role": role,
            },
            recipient_id=invitation.invitation_id if isinstance(invitation.invitation_id, uuid.UUID) else uuid.UUID(str(invitation.invitation_id)),
            recipient_type="CLIENT",
            db=db,
        )
    except Exception:
        logger.exception("invite_user: falha ao enviar email de convite para %s", email)

    return invitation


# ── assign role ──────────────────────────────────────────────────────────────

def assign_role(
    db: Session,
    actor: User,
    target_user_id: UUID,
    new_role: str,
    request_ip: Optional[str] = None,
    request_ua: Optional[str] = None,
) -> User:
    _assert_not_schema_only(new_role)
    _assert_not_platform_owner_by_tenant(actor, new_role)

    # Posse do alvo: mesmo tenant do ator (PLATFORM_OWNER: company_id IS NULL
    # → só usuários de plataforma). 404 idêntico ao de "não existe" — não
    # revelar existência de usuários de outros tenants.
    company_scope = str(actor.company_id) if actor.company_id else None
    target = (
        db.query(User)
        .filter(
            User.id == str(target_user_id),
            User.company_id == company_scope,
            User.active == True,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Actor não pode elevar o próprio role
    if str(actor.id) == str(target.id):
        raise HTTPException(status_code=403, detail="Não é permitido alterar o próprio papel.")

    # Verificar anti-escalonamento
    _assert_can_invite(actor, new_role)

    old_role = target.role
    target.role = new_role

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role=actor.role,
            action="assign_role",
            resource_type="User",
            resource_id=target.id,
            company_id=actor.company_id,
            before_snapshot={"role": old_role},
            after_snapshot={"role": new_role},
            ip_address=request_ip,
            user_agent=request_ua,
        ),
        db,
    )
    db.commit()
    db.refresh(target)
    return target


# ── deactivate ───────────────────────────────────────────────────────────────

def deactivate_user(
    db: Session,
    actor: User,
    target_user_id: UUID,
) -> User:
    # Posse do alvo: mesmo tenant do ator (ver assign_role). active == True
    # segue o padrão do módulo (transfer_ownership) — usuário já inativo é
    # indistinguível de inexistente.
    company_scope = str(actor.company_id) if actor.company_id else None
    target = (
        db.query(User)
        .filter(
            User.id == str(target_user_id),
            User.company_id == company_scope,
            User.active == True,
        )
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    # Restrição: último OWNER ativo não pode ser removido
    if target.role == "OWNER" and target.active:
        if _count_active_owners(db, target.company_id) <= 1:
            raise HTTPException(
                status_code=422,
                detail="Não é possível desativar o último OWNER ativo do tenant.",
            )

    target.active = False
    db.commit()
    db.refresh(target)
    return target


# ── transfer ownership ───────────────────────────────────────────────────────

def transfer_ownership(
    db: Session,
    actor: User,
    new_owner_user_id: UUID,
    current_owner_new_role: str = "ADMIN",
    request_ip: Optional[str] = None,
    request_ua: Optional[str] = None,
) -> User:
    if actor.role != "OWNER":
        raise HTTPException(status_code=403, detail="Apenas o OWNER pode transferir a propriedade.")

    new_owner = (
        db.query(User)
        .filter(
            User.id == str(new_owner_user_id),
            User.company_id == str(actor.company_id) if actor.company_id else None,
            User.active == True,
        )
        .first()
    )
    if not new_owner:
        raise HTTPException(
            status_code=404,
            detail="Usuário destino não encontrado ou não pertence ao tenant.",
        )

    before = {"owner_id": str(actor.id), "role": "OWNER"}

    new_owner.role = "OWNER"
    actor.role = current_owner_new_role

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role="OWNER",
            action="transfer_ownership",
            resource_type="User",
            resource_id=new_owner.id,
            company_id=actor.company_id,
            before_snapshot=before,
            after_snapshot={
                "new_owner_id": str(new_owner_user_id),
                "new_owner_role": "OWNER",
                "previous_owner_new_role": current_owner_new_role,
            },
            ip_address=request_ip,
            user_agent=request_ua,
        ),
        db,
    )
    db.commit()
    db.refresh(actor)
    return new_owner


# ── invitations ──────────────────────────────────────────────────────────────

def list_invitations(db: Session, company_id: UUID) -> List[UserInvitation]:
    return (
        db.query(UserInvitation)
        .filter(
            UserInvitation.company_id == company_id,
            UserInvitation.status == "PENDING",
        )
        .order_by(UserInvitation.created_at.desc())
        .all()
    )


def cancel_invitation(
    db: Session,
    actor: User,
    invitation_id: UUID,
) -> UserInvitation:
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.invitation_id == invitation_id,
            UserInvitation.company_id == actor.company_id,
        )
        .first()
    )
    if not invitation:
        raise HTTPException(status_code=404, detail="Convite não encontrado")
    if invitation.status != "PENDING":
        raise HTTPException(status_code=422, detail="Apenas convites PENDING podem ser cancelados")

    invitation.status = "CANCELLED"
    db.commit()
    db.refresh(invitation)
    return invitation
