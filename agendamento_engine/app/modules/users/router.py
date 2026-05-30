import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import require_role, get_current_user
from app.infrastructure.db.models.user import User
from app.modules.users import schemas, service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["users"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


# ── GET /users ───────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.UserResponse])
def list_users(
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.list_users(db, actor.company_id)


# ── POST /users/invite ────────────────────────────────────────────────────────

@router.post("/invite", response_model=schemas.InviteUserResponse, status_code=201)
def invite_user(
    body: schemas.InviteUserRequest,
    request: Request,
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    ip = _get_real_ip(request)
    ua = request.headers.get("user-agent")
    invitation = service.invite_user(db, actor, body.email, body.role, ip, ua)
    return schemas.InviteUserResponse(
        invitation_id=invitation.invitation_id,
        expires_at=invitation.expires_at,
    )


# ── PATCH /users/{id}/role ────────────────────────────────────────────────────

@router.patch("/{user_id}/role", response_model=schemas.UserResponse)
def assign_role(
    user_id: UUID,
    body: schemas.AssignRoleRequest,
    request: Request,
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    ip = _get_real_ip(request)
    ua = request.headers.get("user-agent")
    return service.assign_role(db, actor, user_id, body.role, ip, ua)


# ── DELETE /users/{id} (desativa) ────────────────────────────────────────────

@router.delete("/{user_id}", response_model=schemas.UserResponse)
def deactivate_user(
    user_id: UUID,
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.deactivate_user(db, actor, user_id)


# ── POST /users/transfer-ownership ───────────────────────────────────────────

@router.post("/transfer-ownership", response_model=schemas.UserResponse)
def transfer_ownership(
    body: schemas.TransferOwnershipRequest,
    request: Request,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ip = _get_real_ip(request)
    ua = request.headers.get("user-agent")
    return service.transfer_ownership(
        db,
        actor,
        body.new_owner_user_id,
        body.current_owner_new_role,
        ip,
        ua,
    )


# ── GET /invitations ──────────────────────────────────────────────────────────

@router.get("/invitations", response_model=List[schemas.InvitationResponse])
def list_invitations(
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.list_invitations(db, actor.company_id)


# ── DELETE /invitations/{id} ──────────────────────────────────────────────────

@router.delete("/invitations/{invitation_id}", response_model=schemas.InvitationResponse)
def cancel_invitation(
    invitation_id: UUID,
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.cancel_invitation(db, actor, invitation_id)


# ── helper ─────────────────────────────────────────────────────────────────

def _get_real_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
