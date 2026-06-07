from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_role
from app.modules.services import schemas, service as svc

router = APIRouter(prefix="/services", tags=["services"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


@router.get("/", response_model=List[schemas.ServiceResponse])
def list_services(
    active_only: bool = True,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_services(db, company_id, active_only=active_only)


@router.post("/", response_model=schemas.ServiceResponse, status_code=201)
def create_service(
    body: schemas.ServiceCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.create_service(db, user.company_id, body)


@router.get("/{service_id}", response_model=schemas.ServiceResponse)
def get_service(
    service_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.get_service_or_404(db, company_id, service_id)


@router.patch("/{service_id}", response_model=schemas.ServiceResponse)
def update_service(
    service_id: UUID,
    body: schemas.ServiceUpdate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.update_service(db, user.company_id, service_id, body)


# ─── Variantes ────────────────────────────────────────────────────────────────

@router.get("/{service_id}/variants", response_model=List[schemas.ServiceVariantResponse])
def list_variants(
    service_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_variants(db, company_id, service_id)


@router.post("/{service_id}/variants", response_model=schemas.ServiceVariantResponse, status_code=201)
def create_variant(
    service_id: UUID,
    body: schemas.ServiceVariantCreate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.create_variant(db, user.company_id, service_id, body)


@router.patch("/{service_id}/variants/{variant_id}", response_model=schemas.ServiceVariantResponse)
def update_variant(
    service_id: UUID,
    variant_id: UUID,
    body: schemas.ServiceVariantUpdate,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return svc.update_variant(db, user.company_id, service_id, variant_id, body)


@router.delete("/{service_id}/variants/{variant_id}", status_code=204)
def delete_variant(
    service_id: UUID,
    variant_id: UUID,
    user=Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    svc.delete_variant(db, user.company_id, service_id, variant_id)
