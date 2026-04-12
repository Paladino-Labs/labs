from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Professional, Service, ProfessionalService
from app.modules.professionals.schemas import (
    ProfessionalCreate,
    ProfessionalUpdate,
    ProfessionalServiceCreate,
    ProfessionalServiceResponse,
)


def list_by_service(db: Session, company_id: UUID, service_id: UUID) -> list[Professional]:
    """
    Retorna profissionais ativos que oferecem um serviço específico.
    Usado pelo bot no estado ESCOLHENDO_PROFISSIONAL.
    """
    return (
        db.query(Professional)
        .join(ProfessionalService, Professional.id == ProfessionalService.professional_id)
        .filter(
            Professional.company_id == company_id,
            Professional.active == True,
            ProfessionalService.service_id == service_id,
            ProfessionalService.company_id == company_id,
        )
        .order_by(Professional.name)
        .all()
    )


def list_professionals(db: Session, company_id: UUID, active_only: bool = True):
    q = db.query(Professional).filter(Professional.company_id == company_id)
    if active_only:
        q = q.filter(Professional.active == True)
    return q.order_by(Professional.name).all()


def get_professional_or_404(db: Session, company_id: UUID, professional_id: UUID) -> Professional:
    p = db.query(Professional).filter(
        Professional.id == professional_id,
        Professional.company_id == company_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return p


def create_professional(db: Session, company_id: UUID, data: ProfessionalCreate) -> Professional:
    p = Professional(company_id=company_id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_professional(
    db: Session, company_id: UUID, professional_id: UUID, data: ProfessionalUpdate
) -> Professional:
    p = get_professional_or_404(db, company_id, professional_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Associação profissional ↔ serviço
# ---------------------------------------------------------------------------

def list_professional_services(
    db: Session, company_id: UUID, professional_id: UUID
) -> list[ProfessionalServiceResponse]:
    get_professional_or_404(db, company_id, professional_id)
    rows = (
        db.query(ProfessionalService, Service)
        .join(Service, ProfessionalService.service_id == Service.id)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.company_id == company_id,
        )
        .all()
    )
    return [
        ProfessionalServiceResponse(
            id=ps.id,
            service_id=svc.id,
            service_name=svc.name,
            price=svc.price,
            duration=svc.duration,
            commission_percentage=ps.commission_percentage,
        )
        for ps, svc in rows
    ]


def add_professional_service(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    data: ProfessionalServiceCreate,
) -> ProfessionalServiceResponse:
    get_professional_or_404(db, company_id, professional_id)

    svc = (
        db.query(Service)
        .filter(Service.id == data.service_id, Service.company_id == company_id)
        .first()
    )
    if not svc:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    existing = (
        db.query(ProfessionalService)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.service_id == data.service_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Associação já existe")

    ps = ProfessionalService(
        company_id=company_id,
        professional_id=professional_id,
        service_id=data.service_id,
        commission_percentage=data.commission_percentage,
    )
    db.add(ps)
    db.commit()
    db.refresh(ps)

    return ProfessionalServiceResponse(
        id=ps.id,
        service_id=svc.id,
        service_name=svc.name,
        price=svc.price,
        duration=svc.duration,
        commission_percentage=ps.commission_percentage,
    )


def remove_professional_service(
    db: Session, company_id: UUID, professional_id: UUID, service_id: UUID
) -> None:
    get_professional_or_404(db, company_id, professional_id)

    ps = (
        db.query(ProfessionalService)
        .filter(
            ProfessionalService.professional_id == professional_id,
            ProfessionalService.service_id == service_id,
            ProfessionalService.company_id == company_id,
        )
        .first()
    )
    if not ps:
        raise HTTPException(status_code=404, detail="Associação não encontrada")

    db.delete(ps)
    db.commit()
