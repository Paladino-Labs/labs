from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exc
from sqlalchemy.orm import Session, joinedload

from app.api.schemas.appointment_response import AppointmentListItem
from app.api.schemas.appointment_schema import AppointmentCreate, CancelSchema, RescheduleSchema
from app.core.deps import get_current_user
from app.db.models import Appointment, AppointmentStatusLog
from app.db.session import get_db
from app.domain.services.appointment_service import change_appointment_status, create_appointment
from app.domain.services.availability_engine import generate_available_slots

router = APIRouter(prefix="/appointments", tags=["Appointments"])


def get_appointment_or_404(db: Session, appointment_id: UUID, company_id):
    appointment = (
        db.query(Appointment)
        .options(
            joinedload(Appointment.client),
            joinedload(Appointment.professional),
            joinedload(Appointment.services),
        )
        .filter(
            Appointment.id == appointment_id,
            Appointment.company_id == company_id,
        )
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return appointment


def reschedule_appointment_fixed(
    db: Session,
    appointment_id: UUID,
    new_start_at: datetime,
    current_user,
):
    appointment = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id,
        )
        .first()
    )
    if not appointment:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")

    if appointment.status in ["completed", "cancelled", "no_show"]:
        raise HTTPException(status_code=400, detail="Agendamento não pode ser remarcado")

    if new_start_at.tzinfo is None:
        new_start_at = new_start_at.replace(tzinfo=timezone.utc)

    if new_start_at < datetime.now(timezone.utc) + timedelta(minutes=30):
        raise HTTPException(status_code=400, detail="Remarcação deve ter pelo menos 30 minutos de antecedência")

    duration = int((appointment.end_at - appointment.start_at).total_seconds() / 60)
    available_slots = generate_available_slots(
        db=db,
        professional_id=appointment.professional_id,
        company_id=appointment.company_id,
        target_date=new_start_at.date(),
        duration_minutes=duration,
        exclude_appointment_id=appointment.id,
    )

    if new_start_at.replace(second=0, microsecond=0) not in [
        slot.replace(second=0, microsecond=0) for slot in available_slots
    ]:
        raise HTTPException(status_code=400, detail="Horário inválido ou indisponível")

    current_version = appointment.version
    old_start = appointment.start_at
    updated = (
        db.query(Appointment)
        .filter(
            Appointment.id == appointment_id,
            Appointment.company_id == current_user.company_id,
            Appointment.version == current_version,
        )
        .update(
            {
                "start_at": new_start_at,
                "end_at": new_start_at + timedelta(minutes=duration),
                "version": current_version + 1,
            }
        )
    )

    if updated == 0:
        raise HTTPException(status_code=409, detail="Conflito de concorrência, tente novamente")

    db.add(
        AppointmentStatusLog(
            company_id=appointment.company_id,
            appointment_id=appointment.id,
            from_status=appointment.status,
            to_status=appointment.status,
            changed_by=current_user.id,
            note=f"Rescheduled from {old_start} to {new_start_at}",
        )
    )
    db.commit()
    return get_appointment_or_404(db, appointment_id, current_user.company_id)


@router.post("/", response_model=AppointmentListItem, status_code=201)
def create(
    data: AppointmentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        appointment = create_appointment(db, data, current_user)
        return get_appointment_or_404(db, appointment.id, current_user.company_id)
    except exc.IntegrityError as e:
        error_msg = str(e.orig).lower()
        if "overlap" in error_msg:
            raise HTTPException(status_code=409, detail="Horário já está ocupado")
        if "idempotency" in error_msg or "uq_idempotency" in error_msg:
            raise HTTPException(status_code=400, detail="Requisição duplicada")
        raise HTTPException(status_code=400, detail="Erro ao criar agendamento")


@router.get("/", response_model=list[AppointmentListItem])
def list_appointments(
    date: str | None = None,
    professional_id: UUID | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = (
        db.query(Appointment)
        .options(
            joinedload(Appointment.client),
            joinedload(Appointment.professional),
            joinedload(Appointment.services),
        )
        .filter(Appointment.company_id == current_user.company_id)
    )

    if professional_id:
        query = query.filter(Appointment.professional_id == professional_id)

    if date:
        target_date = datetime.fromisoformat(date).date()
        start_of_day = datetime.combine(target_date, datetime.min.time(), timezone.utc)
        end_of_day = start_of_day + timedelta(days=1)
        query = query.filter(
            Appointment.start_at >= start_of_day,
            Appointment.start_at < end_of_day,
        )

    return query.order_by(Appointment.start_at).all()


@router.get("/{appointment_id}", response_model=AppointmentListItem)
def get_appointment(
    appointment_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_appointment_or_404(db, appointment_id, current_user.company_id)


@router.patch("/{appointment_id}/status")
def update_status(
    appointment_id: UUID,
    new_status: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    appointment = change_appointment_status(db, appointment_id, new_status, current_user)
    return {"id": str(appointment.id), "status": appointment.status}


@router.patch("/{appointment_id}/cancel")
def cancel(
    appointment_id: UUID,
    data: CancelSchema,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    appointment = change_appointment_status(
        db,
        appointment_id,
        "cancelled",
        current_user,
        note=data.reason,
    )
    return {"id": str(appointment.id), "status": appointment.status}


@router.patch("/{appointment_id}/reschedule", response_model=AppointmentListItem)
def reschedule(
    appointment_id: UUID,
    data: RescheduleSchema,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return reschedule_appointment_fixed(db, appointment_id, data.start_at, current_user)
