from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Appointment, AvailabilitySlot, BlockedSlot, WorkingHour
from app.domain.constants.appointments_constants import ACTIVE_STATUSES


def generate_available_slots(
    db: Session,
    professional_id: UUID,
    company_id: UUID,
    target_date: date,
    duration_minutes: int,
    exclude_appointment_id: UUID | None = None,
):
    weekday = target_date.weekday()

    working_hours = (
        db.query(WorkingHour)
        .filter(
            WorkingHour.professional_id == professional_id,
            WorkingHour.company_id == company_id,
            WorkingHour.weekday == weekday,
            WorkingHour.is_active == True,
        )
        .first()
    )

    if not working_hours:
        return []

    start_datetime = datetime.combine(target_date, working_hours.opening_time, timezone.utc)
    end_datetime = datetime.combine(target_date, working_hours.closing_time, timezone.utc)

    slot_interval = 15
    slots = []
    current = start_datetime
    delta = timedelta(minutes=duration_minutes)
    step = timedelta(minutes=slot_interval)

    while current + delta <= end_datetime:
        slots.append((current, current + delta))
        current += step

    blocked = (
        db.query(BlockedSlot)
        .filter(
            BlockedSlot.professional_id == professional_id,
            BlockedSlot.company_id == company_id,
            BlockedSlot.start_at < end_datetime,
            BlockedSlot.end_at > start_datetime,
        )
        .all()
    )
    blocked_ranges = [(b.start_at, b.end_at) for b in blocked]

    query = (
        db.query(Appointment)
        .filter(
            Appointment.professional_id == professional_id,
            Appointment.company_id == company_id,
            Appointment.start_at < end_datetime,
            Appointment.end_at > start_datetime,
            Appointment.status.in_(ACTIVE_STATUSES),
        )
    )

    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)

    appointments = query.all()
    appointment_ranges = [(a.start_at, a.end_at) for a in appointments]
    cutoff = datetime.now(timezone.utc) + timedelta(minutes=30)

    available = []
    for slot_start, slot_end in slots:
        if slot_start < cutoff:
            continue
        if any(slot_start < end and slot_end > start for start, end in blocked_ranges):
            continue
        if any(slot_start < end and slot_end > start for start, end in appointment_ranges):
            continue
        available.append(slot_start)

    sync_availability_cache(
        db=db,
        professional_id=professional_id,
        company_id=company_id,
        target_date=target_date,
        duration_minutes=duration_minutes,
        available_slots=available,
    )

    return available


def sync_availability_cache(
    db: Session,
    professional_id: UUID,
    company_id: UUID,
    target_date: date,
    duration_minutes: int,
    available_slots: list[datetime],
):
    start_of_day = datetime.combine(target_date, datetime.min.time(), timezone.utc)
    end_of_day = start_of_day + timedelta(days=1)

    db.query(AvailabilitySlot).filter(
        AvailabilitySlot.company_id == company_id,
        AvailabilitySlot.professional_id == professional_id,
        AvailabilitySlot.start_at >= start_of_day,
        AvailabilitySlot.start_at < end_of_day,
    ).delete()

    for slot_start in available_slots:
        db.add(
            AvailabilitySlot(
                company_id=company_id,
                professional_id=professional_id,
                start_at=slot_start,
                end_at=slot_start + timedelta(minutes=duration_minutes),
                status="AVAILABLE",
            )
        )

    db.flush()
