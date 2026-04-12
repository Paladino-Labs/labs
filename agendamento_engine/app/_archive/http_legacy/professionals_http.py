from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas.professional_schema import (
    ProfessionalCreate,
    ProfessionalOut,
    ProfessionalServiceLinkRequest,
    ProfessionalServiceOut,
    ProfessionalUpdate,
)
from app.core.deps import get_current_user
from app.db.models import ProfessionalService, Service
from app.db.session import get_db
from app.modules.professionals.service import (
    create_professional,
    get_professional_or_404,
    list_professionals,
    update_professional,
)

router = APIRouter(prefix="/professionals", tags=["Professionals"])


@router.post("/", response_model=ProfessionalOut, status_code=201)
def create_professional_endpoint(
    data: ProfessionalCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_professional(db, current_user.company_id, data)


@router.get("/", response_model=list[ProfessionalOut])
def list_professionals_endpoint(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return list_professionals(db, current_user.company_id)


@router.get("/{professional_id}", response_model=ProfessionalOut)
def get_professional_endpoint(
    professional_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_professional_or_404(db, current_user.company_id, professional_id)


@router.patch("/{professional_id}", response_model=ProfessionalOut)
def update_professional_endpoint(
    professional_id: UUID,
    data: ProfessionalUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    professional = get_professional_or_404(db, current_user.company_id, professional_id)
    return update_professional(db, professional, data)


def _load_linked_services(db: Session, company_id, professional_id):
    return (
        db.query(Service)
        .join(
            ProfessionalService,
            ProfessionalService.service_id == Service.id,
        )
        .filter(
            ProfessionalService.professional_id == professional_id,
            Service.company_id == company_id,
        )
        .order_by(Service.name.asc())
        .all()
    )


@router.get("/{professional_id}/services", response_model=list[ProfessionalServiceOut])
def get_professional_services(
    professional_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    get_professional_or_404(db, current_user.company_id, professional_id)
    return _load_linked_services(db, current_user.company_id, professional_id)


@router.post("/{professional_id}/services", response_model=list[ProfessionalServiceOut])
def add_professional_services(
    professional_id: UUID,
    data: ProfessionalServiceLinkRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    get_professional_or_404(db, current_user.company_id, professional_id)

    existing_ids = {
        row.service_id
        for row in db.query(ProfessionalService)
        .filter(
            ProfessionalService.professional_id == professional_id,
        )
        .all()
    }

    services = (
        db.query(Service)
        .filter(
            Service.company_id == current_user.company_id,
            Service.id.in_(data.service_ids),
        )
        .all()
    )

    for service in services:
        if service.id in existing_ids:
            continue

        db.add(
            ProfessionalService(
                company_id=current_user.company_id,
                professional_id=professional_id,
                service_id=service.id,
            )
        )

    db.commit()
    return _load_linked_services(db, current_user.company_id, professional_id)


@router.put("/{professional_id}/services", response_model=list[ProfessionalServiceOut])
def replace_professional_services(
    professional_id: UUID,
    data: ProfessionalServiceLinkRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    get_professional_or_404(db, current_user.company_id, professional_id)

    db.query(ProfessionalService).filter(
        ProfessionalService.professional_id == professional_id,
    ).delete()

    services = (
        db.query(Service)
        .filter(
            Service.company_id == current_user.company_id,
            Service.id.in_(data.service_ids),
        )
        .all()
    )

    for service in services:
        db.add(
            ProfessionalService(
                company_id=current_user.company_id,
                professional_id=professional_id,
                service_id=service.id,
            )
        )

    db.commit()
    return _load_linked_services(db, current_user.company_id, professional_id)
