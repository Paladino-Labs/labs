from datetime import datetime, timedelta, timezone, date
from sqlalchemy.orm import Session
from uuid import UUID

from app.db.models import (
    WorkingHour,
    BlockedSlot,
    Appointment
)

from app.domain.constants.appointments_constants import ACTIVE_STATUSES


def generate_available_slots(
    db: Session,
    professional_id: UUID,
    company_id: UUID,
    target_date: date,
    duration_minutes: int,
    exclude_appointment_id: UUID | None = None
):
    """
    Retorna os horários disponíveis de um profissional em um dia específico
    """

    weekday = target_date.weekday()

    # TODO: suportar múltiplos intervalos por dia
    working_hours = (
        db.query(WorkingHour)
        .filter(
            WorkingHour.professional_id == professional_id,
            WorkingHour.company_id == company_id,
            WorkingHour.weekday == weekday,
            WorkingHour.is_active == True
        )
        .first()
    )

    if not working_hours:
        return []

    tz = timezone.utc

    start_datetime = datetime.combine(
        target_date,
        working_hours.opening_time,
        tz
    )

    end_datetime = datetime.combine(
        target_date,
        working_hours.closing_time,
        tz
    )

    # ⏱️ Slots
    slot_interval = 5  # TODO: tornar configurável
    slots = []

    current = start_datetime
    delta = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=slot_interval)

    while current + delta <= end_datetime:
        slots.append((current, current + delta))
        current += step

    # 🚫 Bloqueios
    blocked = (
        db.query(BlockedSlot)
        .filter(
            BlockedSlot.professional_id == professional_id,
            BlockedSlot.company_id == company_id,
            BlockedSlot.start_at < end_datetime,
            BlockedSlot.end_at > start_datetime
        )
        .all()
    )

    blocked_ranges = [(b.start_at, b.end_at) for b in blocked]

    # 📅 Agendamentos
    query = (
        db.query(Appointment)
        .filter(
            Appointment.professional_id == professional_id,
            Appointment.company_id == company_id,
            Appointment.start_at < end_datetime,
            Appointment.end_at > start_datetime,
            Appointment.status.in_(ACTIVE_STATUSES)
        )
    )

    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)

    appointments = query.all()
    appointment_ranges = [(a.start_at, a.end_at) for a in appointments]

    # ⏳ Antecedência
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(minutes=30)

    available = []

    for slot_start, slot_end in slots:

        if slot_start < cutoff:
            continue

        if any(slot_start < end and slot_end > start for start, end in blocked_ranges):
            continue

        if any(slot_start < end and slot_end > start for start, end in appointment_ranges):
            continue

        available.append(slot_start)

    return available