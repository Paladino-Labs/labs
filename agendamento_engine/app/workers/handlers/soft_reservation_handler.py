"""
Handler para agenda.soft_reservation.expired — Sprint 10.

Primeiro registro deste handler no sistema.

Comportamento:
  - Busca o appointment vinculado à reservation expirada.
  - Se appointment em DRAFT ou REQUESTED: cancela (status = CANCELLED).
  - Emite appointment.cancelled best-effort via EventBus.
  - Idempotente: reservation já EXPIRED (sem appointment ou já cancelado) → sem erro.
"""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def handle_soft_reservation_expired(event) -> None:
    """Handler para agenda.soft_reservation.expired."""
    payload = event.payload
    reservation_id_str: str = payload.get("reservation_id")
    company_id_str: str = payload.get("company_id")

    if not reservation_id_str:
        logger.error(
            "handle_soft_reservation_expired: payload sem reservation_id event_id=%s",
            event.event_id,
        )
        return

    db: Session = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        company_id = UUID(company_id_str) if company_id_str else None
        set_rls_context(db, company_id)

        from app.infrastructure.db.models.reservation import Reservation
        from app.infrastructure.db.models.appointment import Appointment

        reservation = (
            db.query(Reservation)
            .filter(Reservation.reservation_id == UUID(reservation_id_str))
            .first()
        )

        if reservation is None:
            logger.debug(
                "handle_soft_reservation_expired: reserva não encontrada reservation_id=%s",
                reservation_id_str,
            )
            return  # idempotente

        if reservation.status != "EXPIRED":
            # Reserva ainda não expirada — pode ser race condition; sem erro
            logger.debug(
                "handle_soft_reservation_expired: reserva não está EXPIRED status=%s reservation_id=%s",
                reservation.status, reservation_id_str,
            )
            return

        if reservation.appointment_id is None:
            logger.debug(
                "handle_soft_reservation_expired: sem appointment vinculado reservation_id=%s",
                reservation_id_str,
            )
            return

        appointment = (
            db.query(Appointment)
            .filter(
                Appointment.id == reservation.appointment_id,
                Appointment.company_id == reservation.company_id,
            )
            .with_for_update(skip_locked=True)
            .first()
        )

        if appointment is None:
            logger.debug(
                "handle_soft_reservation_expired: appointment não encontrado ou locked appointment_id=%s",
                str(reservation.appointment_id),
            )
            return

        if appointment.status not in ("DRAFT", "REQUESTED", "SCHEDULED"):
            # Já em estado terminal ou avançado — idempotente
            logger.debug(
                "handle_soft_reservation_expired: appointment em status=%s — sem ação",
                appointment.status,
            )
            return

        appointment.status = "CANCELLED"
        db.commit()

        logger.info(
            "handle_soft_reservation_expired: appointment %s CANCELLED por expiração de SOFT %s",
            str(reservation.appointment_id), reservation_id_str,
        )

        # Emite best-effort (EventBus in-process) — falha não impacta o cancelamento
        try:
            import uuid as _uuid
            from datetime import datetime, timezone
            from app.infrastructure.event_bus import DomainEvent, event_bus

            event_bus.publish(DomainEvent(
                event_id=_uuid.uuid4(),
                event_type="appointment.cancelled",
                occurred_at=datetime.now(timezone.utc),
                company_id=reservation.company_id,
                idempotency_key=f"appointment.cancelled.soft_expired:{reservation.appointment_id}",
                actor={"type": "SYSTEM", "id": None},
                payload={"appointment_id": str(reservation.appointment_id)},
            ))
        except Exception:
            logger.exception(
                "handle_soft_reservation_expired: falha ao publicar appointment.cancelled (best-effort)"
            )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_soft_reservation_expired: erro reservation_id=%s event_id=%s",
            reservation_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra o handler agenda.soft_reservation.expired no EventBus global."""
    from app.infrastructure.event_bus import event_bus
    event_bus.register("agenda.soft_reservation.expired", handle_soft_reservation_expired)
    logger.info("soft_reservation_handler: handler registrado")
