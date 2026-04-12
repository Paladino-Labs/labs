from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.infrastructure.db.models.user import User
from app.modules.professionals import schemas, service

router = APIRouter(prefix="/professionals", tags=["professionals"])


@router.get("/", response_model=List[schemas.ProfessionalResponse])
def list_professionals(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.list_professionals(db, company_id)


@router.post("/", response_model=schemas.ProfessionalResponse, status_code=201)
def create_professional(
    body: schemas.ProfessionalCreate,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.create_professional(db, user.company_id, body)


@router.get("/{professional_id}", response_model=schemas.ProfessionalResponse)
def get_professional(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.get_professional_or_404(db, company_id, professional_id)


@router.patch("/{professional_id}", response_model=schemas.ProfessionalResponse)
def update_professional(
    professional_id: UUID,
    body: schemas.ProfessionalUpdate,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return service.update_professional(db, user.company_id, professional_id, body)


# ---------------------------------------------------------------------------
# Associação profissional ↔ serviço
# ---------------------------------------------------------------------------

@router.get(
    "/{professional_id}/services",
    response_model=List[schemas.ProfessionalServiceResponse],
)
def list_professional_services(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    """Lista os serviços associados ao profissional."""
    return service.list_professional_services(db, company_id, professional_id)


@router.post(
    "/{professional_id}/services",
    response_model=schemas.ProfessionalServiceResponse,
    status_code=201,
)
def add_professional_service(
    professional_id: UUID,
    body: schemas.ProfessionalServiceCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Associa um serviço ao profissional. Restrito a admins."""
    return service.add_professional_service(db, admin.company_id, professional_id, body)


@router.delete("/{professional_id}/services/{service_id}", status_code=204)
def remove_professional_service(
    professional_id: UUID,
    service_id: UUID,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Remove a associação entre profissional e serviço. Restrito a admins."""
    service.remove_professional_service(db, admin.company_id, professional_id, service_id)
