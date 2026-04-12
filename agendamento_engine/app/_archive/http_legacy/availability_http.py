from datetime import date as date_module, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.models import Professional, ProfessionalService, Service
from app.db.session import get_db
from app.domain.services.availability_engine import generate_available_slots

router = APIRouter()


def _load_availability(db: Session, professional_id: UUID, service_id: UUID, target_date):
    professional = db.query(Professional).filter(
        Professional.id == professional_id,
        Professional.active == True,
    ).first()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    company_id = professional.company_id
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.company_id == company_id,
        Service.active == True,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    link = db.query(ProfessionalService).filter(
        ProfessionalService.professional_id == professional_id,
        ProfessionalService.service_id == service_id,
        ProfessionalService.company_id == company_id,
    ).first()
    if not link:
        raise HTTPException(status_code=400, detail="Profissional não executa esse serviço")

    slots = generate_available_slots(
        db=db,
        professional_id=professional_id,
        company_id=company_id,
        target_date=target_date,
        duration_minutes=service.duration,
    )
    return company_id, service, slots


@router.get("/availability")
def get_availability(
    professional_id: UUID,
    service_id: UUID,
    date: str = Query(..., description="Formato: YYYY-MM-DD"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        response_date = date_module.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida, use formato YYYY-MM-DD")

    company_id, service, slots = _load_availability(db, professional_id, service_id, response_date)
    if company_id != current_user.company_id:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    return {
        "date": response_date.isoformat(),
        "professional_id": str(professional_id),
        "service_ids": [str(service_id)],
        "slot_duration_minutes": service.duration,
        "available_slots": [
            {
                "start_at": slot.isoformat(),
                "end_at": (slot + timedelta(minutes=service.duration)).isoformat(),
                "label": slot.strftime("%H:%M"),
            }
            for slot in slots
        ],
    }


@router.get("/")
def legacy_get_availability(
    professional_id: UUID,
    service_id: UUID,
    target_date: str = Query(..., description="Formato: YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    try:
        response_date = date_module.fromisoformat(target_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida, use formato YYYY-MM-DD")

    _, service, slots = _load_availability(db, professional_id, service_id, response_date)
    return [
        {
            "start_at": slot.isoformat(),
            "end_at": (slot + timedelta(minutes=service.duration)).isoformat(),
        }
        for slot in slots
    ]
