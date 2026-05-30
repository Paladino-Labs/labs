import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

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

def invite_user(
    db: Session,
    actor: User,
    email: str,
    role: str,
    request_ip: Optional[str] = None,
    request_ua: Optional[str] = None,
) -> UserInvitation:
    _assert_not_schema_only(role)
    _assert_not_platform_owner_by_tenant(actor, role)
    _assert_can_invite(actor, role)

    # Actor não pode elevar o próprio papel via convite (convite cria usuário novo,
    # mas a verificação de autoelevação aplica-se a assign_role)

    def _s(v):
        return str(v) if v is not None else None

    invitation = UserInvitation(
        invitation_id=_s(uuid.uuid4()),
        company_id=_s(actor.company_id),  # NULL para PLATFORM_OWNER
        email=email,
        role=role,
        token=_s(uuid.uuid4()),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
        status="PENDING",
        invited_by_user_id=_s(actor.id),
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

    target = db.query(User).filter(User.id == str(target_user_id), User.active == True).first()
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
    target = db.query(User).filter(User.id == str(target_user_id)).first()
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
