from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.deps import require_role, get_current_user, get_current_company_id
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import User
from app.modules.integrations import service
from app.modules.integrations.schemas import (
    CredentialCreate,
    CredentialRotate,
    CredentialResponse,
    TestConnectionResponse,
)

router = APIRouter(prefix="/integrations/credentials", tags=["integrations"])


def _ip(request: Request) -> str | None:
    xff = request.headers.get("X-Forwarded-For")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("", response_model=CredentialResponse, status_code=201)
def create_credential(
    body: CredentialCreate,
    request: Request,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    cred = service.create_credential(
        db=db,
        company_id=company_id,
        actor_id=user.id,
        actor_role=user.role,
        provider=body.provider,
        label=body.label,
        secret=body.secret,
        config=body.config,
        ip_address=_ip(request),
    )
    return cred


@router.get("", response_model=list[CredentialResponse])
def list_credentials(
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.list_credentials(db=db, company_id=company_id)


@router.post("/{credential_id}/rotate", response_model=CredentialResponse)
def rotate_credential(
    credential_id: UUID,
    body: CredentialRotate,
    request: Request,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.rotate_credential(
        db=db,
        company_id=company_id,
        credential_id=credential_id,
        actor_id=user.id,
        actor_role=user.role,
        new_secret=body.new_secret,
        ip_address=_ip(request),
    )


@router.post("/{credential_id}/revoke", status_code=204)
def revoke_credential(
    credential_id: UUID,
    request: Request,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    service.revoke_credential(
        db=db,
        company_id=company_id,
        credential_id=credential_id,
        actor_id=user.id,
        actor_role=user.role,
        ip_address=_ip(request),
    )


@router.post("/{credential_id}/test", response_model=TestConnectionResponse)
def test_credential(
    credential_id: UUID,
    request: Request,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    result = service.test_credential(
        db=db,
        company_id=company_id,
        credential_id=credential_id,
        actor_id=user.id,
        actor_role=user.role,
        ip_address=_ip(request),
    )
    db.commit()
    return result
