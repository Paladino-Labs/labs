from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db.models import (
    Appointment, Customer, Professional, Service, WorkingHour, ScheduleBlock,
)
from app.domain.enums import AppointmentStatus, FinancialStatus
from app.modules.appointments.schemas import AppointmentCreate, RescheduleRequest
from app.modules.appointments.snapshots import build_snapshots
from app.modules.appointments.transitions import transition
from app.modules.appointments.polices import (
    PolicyViolationError,
    CANCELLATION_TOO_LATE, RESCHEDULE_TOO_LATE,
    check_cancellation_policy, check_reschedule_policy,
)
from app.core.config import settings


def _assert_slot_available(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_appointment_id: UUID | None = None,
) -> None:
    """
    Defense-in-depth: verifica se o slot [start_at, end_at) está disponível
    antes de tentar persistir. Levanta 422 para restrições de horário e 409
    para conflitos com agendamentos ou bloqueios existentes.

    O EXCLUDE CONSTRAINT no banco permanece como última barreira — esta
    verificação torna o erro detectável antes do commit, com mensagem clara.
    """
    weekday = start_at.weekday()

    # 1. Profissional trabalha neste dia?
    working_hour = db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == professional_id,
        WorkingHour.weekday == weekday,
        WorkingHour.is_active == True,
    ).first()

    if not working_hour:
        raise HTTPException(
            status_code=422,
            detail="Profissional não atende neste dia da semana",
        )

    # 2. Slot dentro da janela de trabalho?
    day_start = datetime.combine(start_at.date(), working_hour.opening_time, tzinfo=timezone.utc)
    day_end   = datetime.combine(start_at.date(), working_hour.closing_time, tzinfo=timezone.utc)

    if start_at < day_start or end_at > day_end:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Horário fora da janela de trabalho do profissional "
                f"({working_hour.opening_time.strftime('%H:%M')}–"
                f"{working_hour.closing_time.strftime('%H:%M')} UTC)"
            ),
        )

    # 3. Conflito com agendamentos ativos?
    overlap_q = db.query(Appointment).filter(
        Appointment.company_id == company_id,
        Appointment.professional_id == professional_id,
        Appointment.status.notin_(["CANCELLED", "NO_SHOW"]),
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_appointment_id:
        overlap_q = overlap_q.filter(Appointment.id != exclude_appointment_id)

    if overlap_q.first():
        raise HTTPException(
            status_code=409,
            detail="Horário já ocupado por outro agendamento",
        )

    # 4. Conflito com bloqueios manuais?
    block = db.query(ScheduleBlock).filter(
        ScheduleBlock.company_id == company_id,
        ScheduleBlock.professional_id == professional_id,
        ScheduleBlock.start_at < end_at,
        ScheduleBlock.end_at > start_at,
    ).first()

    if block:
        raise HTTPException(
            status_code=409,
            detail="Horário bloqueado na agenda do profissional",
        )


def list_appointments(db: Session, company_id: UUID):
    return (
        db.query(Appointment)
        .filter(Appointment.company_id == company_id)
        .order_by(Appointment.start_at.desc())
        .all()
    )


def get_appointment_or_404(db: Session, company_id: UUID, appointment_id: UUID) -> Appointment:
    a = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.company_id == company_id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return a


def list_active_by_client(
    db: Session, company_id: UUID, client_id: UUID
) -> list[Appointment]:
    """
    Retorna agendamentos futuros ativos de um cliente.
    Usado pelo bot no estado VER_AGENDAMENTOS.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == client_id,
            Appointment.status.in_(["SCHEDULED", "IN_PROGRESS"]),
            Appointment.start_at > now,
        )
        .order_by(Appointment.start_at.asc())
        .all()
    )


def list_completed_by_client(
    db: Session, company_id: UUID, client_id: UUID, limit: int = 1
) -> list[Appointment]:
    """
    Retorna os últimos agendamentos concluídos de um cliente.
    Usado pelo bot para detectar cliente recorrente e montar onboarding preditivo.
    """
    return (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == client_id,
            Appointment.status == "COMPLETED",
        )
        .order_by(Appointment.start_at.desc())
        .limit(limit)
        .all()
    )


def create_appointment(
    db: Session, company_id: UUID, data: AppointmentCreate, user_id: UUID | None = None
) -> Appointment:
    # Valida profissional
    professional = db.query(Professional).filter(
        Professional.id == data.professional_id,
        Professional.company_id == company_id,
        Professional.active == True,
    ).first()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    # Valida cliente
    customer = db.query(Customer).filter(
        Customer.id == data.client_id,
        Customer.company_id == company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Valida e carrega serviços
    service_ids = [s.service_id for s in data.services]
    services = db.query(Service).filter(
        Service.id.in_(service_ids),
        Service.company_id == company_id,
        Service.active == True,
    ).all()

    if len(services) != len(service_ids):
        raise HTTPException(status_code=404, detail="Um ou mais serviços não encontrados")

    # Constrói snapshots e calcula valores
    snapshots, subtotal, total_minutes = build_snapshots(services)
    end_at = data.start_at + timedelta(minutes=total_minutes)

    # Defense in depth: verifica disponibilidade antes do INSERT
    _assert_slot_available(db, company_id, data.professional_id, data.start_at, end_at)

    appointment = Appointment(
        company_id=company_id,
        professional_id=data.professional_id,
        client_id=data.client_id,
        start_at=data.start_at,
        end_at=end_at,
        subtotal_amount=subtotal,
        discount_amount=Decimal("0"),
        total_amount=subtotal,
        total_commission=Decimal("0"),
        status=AppointmentStatus.SCHEDULED.value,
        financial_status=FinancialStatus.UNPAID.value,
        idempotency_key=data.idempotency_key,
    )

    for snap in snapshots:
        appointment.services.append(snap)

    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Agendamento duplicado (idempotency_key já usado)")

    db.refresh(appointment)
    return appointment


def cancel_appointment(
    db: Session, company_id: UUID, appointment_id: UUID,
    user_id: UUID | None = None, reason: str = None,
    skip_policy: bool = False,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)

    if not skip_policy:
        allowed, msg = check_cancellation_policy(
            start_at=appointment.start_at,
            now=datetime.now(timezone.utc),
            min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
        )
        if not allowed:
            raise PolicyViolationError(code=CANCELLATION_TOO_LATE, detail=msg)

    transition(db, appointment, AppointmentStatus.CANCELLED, changed_by_id=user_id, note=reason)
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancelled_by = user_id
    appointment.cancel_reason = reason
    db.commit()
    db.refresh(appointment)
    return appointment


def reschedule_appointment(
    db: Session, company_id: UUID, appointment_id: UUID,
    data: RescheduleRequest, user_id: UUID | None = None,
    skip_policy: bool = False,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)

    if AppointmentStatus(appointment.status).is_terminal:
        raise HTTPException(status_code=409, detail="Não é possível remarcar um agendamento encerrado")

    if not skip_policy:
        allowed, msg = check_reschedule_policy(
            start_at=appointment.start_at,
            now=datetime.now(timezone.utc),
            min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE,
        )
        if not allowed:
            raise PolicyViolationError(code=RESCHEDULE_TOO_LATE, detail=msg)

    total_minutes = sum(int(s.duration_snapshot) for s in appointment.services)
    new_end_at = data.start_at + timedelta(minutes=total_minutes)

    # Defense in depth: verifica disponibilidade excluindo o próprio agendamento
    _assert_slot_available(
        db, company_id, appointment.professional_id,
        data.start_at, new_end_at,
        exclude_appointment_id=appointment_id,
    )

    appointment.start_at = data.start_at
    appointment.end_at = new_end_at

    db.commit()
    db.refresh(appointment)
    return appointment
