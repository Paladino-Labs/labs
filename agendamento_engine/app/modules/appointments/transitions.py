import logging

from fastapi import HTTPException

from app.domain.enums import AppointmentStatus
from app.infrastructure.db.models import Appointment, AppointmentStatusLog

logger = logging.getLogger(__name__)


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

    # Publica operation.completed quando status → COMPLETED (best-effort, pós-flush)
    if to_status.value == "COMPLETED":
        _publish_operation_completed(appointment)

    return appointment


def _publish_operation_completed(appointment: Appointment) -> None:
    """Emite operation.completed via EventBus — best-effort, falha não afeta a transição."""
    try:
        import uuid as _uuid
        from datetime import datetime, timezone
        from decimal import Decimal

        from app.infrastructure.event_bus import DomainEvent, event_bus

        # Resolve gross_amount e service_id a partir do appointment
        gross_amount = Decimal("0")
        service_id = None

        if hasattr(appointment, "services") and appointment.services:
            for svc in appointment.services:
                if svc.price is not None:
                    gross_amount += Decimal(str(svc.price))
                if service_id is None and svc.service_id is not None:
                    service_id = svc.service_id
        elif appointment.price is not None:
            gross_amount = Decimal(str(appointment.price))

        event_bus.publish(DomainEvent(
            event_id=_uuid.uuid4(),
            event_type="operation.completed",
            occurred_at=datetime.now(timezone.utc),
            company_id=appointment.company_id,
            idempotency_key=f"operation.completed:{appointment.id}",
            actor={"type": "SYSTEM", "id": None},
            payload={
                "appointment_id": str(appointment.id),
                "professional_id": str(appointment.professional_id) if appointment.professional_id else None,
                "service_id": str(service_id) if service_id else None,
                "gross_amount": str(gross_amount),
                "provider_fee": "0",
                "company_id": str(appointment.company_id),
            },
        ))
    except Exception:
        logger.exception(
            "_publish_operation_completed: falha ao publicar evento appointment_id=%s",
            appointment.id,
        )
