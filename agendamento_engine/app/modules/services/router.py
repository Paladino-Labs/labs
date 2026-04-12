from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.modules.services import schemas, service as svc

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/", response_model=List[schemas.ServiceResponse])
def list_services(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_services(db, company_id)


@router.post("/", response_model=schemas.ServiceResponse, status_code=201)
def create_service(
    body: schemas.ServiceCreate,
    user=Depends(require_admin),
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
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return svc.update_service(db, user.company_id, service_id, body)
