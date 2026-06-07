"""
Endpoints de pricing overrides por profissional.
Prefixo: /professionals/{id}/pricing-overrides
"""
from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_role
from app.modules.services import schemas as svc_schemas
from app.modules.services import service as svc

router = APIRouter(prefix="/professionals", tags=["pricing-overrides"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


@router.get(
    "/{professional_id}/pricing-overrides",
    response_model=List[svc_schemas.PricingOverrideResponse],
)
def list_overrides(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_overrides(db, company_id, professional_id)


@router.post(
    "/{professional_id}/pricing-overrides",
    response_model=svc_schemas.PricingOverrideResponse,
    status_code=201,
)
def create_override(
    professional_id: UUID,
    body: svc_schemas.PricingOverrideCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.create_override(db, user.company_id, professional_id, body)


@router.patch(
    "/{professional_id}/pricing-overrides/{override_id}",
    response_model=svc_schemas.PricingOverrideResponse,
)
def update_override(
    professional_id: UUID,
    override_id: UUID,
    body: svc_schemas.PricingOverrideUpdate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.update_override(db, user.company_id, professional_id, override_id, body)


@router.delete(
    "/{professional_id}/pricing-overrides/{override_id}",
    status_code=204,
)
def delete_override(
    professional_id: UUID,
    override_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    svc.delete_override(db, user.company_id, professional_id, override_id)
