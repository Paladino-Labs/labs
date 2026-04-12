from fastapi import HTTPException

from app.domain.enums import AppointmentStatus
from app.infrastructure.db.models import Appointment, AppointmentStatusLog


def transition(
    db,
    appointment: Appointment,
    to_status: AppointmentStatus,
    changed_by_id=None,
    note: str = None,
) -> Appointment:
    current = AppointmentStatus(appointment.status)

    if current.is_terminal:
        raise HTTPException(
            status_code=409,
            detail=f"Agendamento já está em estado terminal: {current.value}",
        )

    allowed = current.allowed_transitions
    if to_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Transição inválida: {current.value} → {to_status.value}",
        )

    log = AppointmentStatusLog(
        company_id=appointment.company_id,
        appointment_id=appointment.id,
        from_status=appointment.status,
        to_status=to_status.value,
        changed_by=changed_by_id,
        note=note,
    )
    db.add(log)

    appointment.status = to_status.value
    appointment.version += 1

    return appointment
