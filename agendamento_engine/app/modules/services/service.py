from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Service
from app.modules.services.schemas import ServiceCreate, ServiceUpdate


def list_services(db: Session, company_id: UUID, active_only: bool = True):
    q = db.query(Service).filter(Service.company_id == company_id)
    if active_only:
        q = q.filter(Service.active == True)
    return q.order_by(Service.name).all()


def get_service_or_404(db: Session, company_id: UUID, service_id: UUID) -> Service:
    s = db.query(Service).filter(
        Service.id == service_id,
        Service.company_id == company_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return s


def create_service(db: Session, company_id: UUID, data: ServiceCreate) -> Service:
    s = Service(company_id=company_id, **data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_service(db: Session, company_id: UUID, service_id: UUID, data: ServiceUpdate) -> Service:
    s = get_service_or_404(db, company_id, service_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s
