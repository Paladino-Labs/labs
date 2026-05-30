"""
Handlers de eventos para booking_session — registrados no EventBus no startup.

booking_session.expired:
  Idempotency key: booking_session.expired:{booking_session_id}  (Padrão A)
  Consumer: "booking_session_cleanup"
  Ação: marca sessão como EXPIRED, libera slot ocupado pelo TTL.
"""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.idempotency import is_processed, mark_processed
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models.booking_session import BookingSession

logger = logging.getLogger(__name__)

_CONSUMER = "booking_session_cleanup"


def handle_booking_session_expired(event) -> None:
    """
    Handler para booking_session.expired.
    Executa síncronamente no mesmo processo que publicou o evento.
    """
    booking_session_id_str: str = event.payload.get("booking_session_id")
    if not booking_session_id_str:
        logger.error("handle_booking_session_expired: payload sem booking_session_id event_id=%s", event.event_id)
        return

    db: Session = SessionLocal()
    try:
        if is_processed(event.idempotency_key, _CONSUMER, db):
            logger.debug(
                "handle_booking_session_expired: já processado key=%s", event.idempotency_key
            )
            return

        session = (
            db.query(BookingSession)
            .filter(BookingSession.id == UUID(booking_session_id_str))
            .with_for_update(skip_locked=True)
            .first()
        )

        if session is None:
            # Sessão deletada ou locked por outro processo — registrar como processado
            mark_processed(
                key=event.idempotency_key,
                consumer=_CONSUMER,
                event_id=event.event_id,
                db=db,
                company_id=event.company_id,
                result_summary="session_not_found",
            )
            db.commit()
            return

        if session.state in {"CONFIRMED", "EXPIRED", "CANCELLED", "ERROR"}:
            # Já em estado terminal — idempotente
            mark_processed(
                key=event.idempotency_key,
                consumer=_CONSUMER,
                event_id=event.event_id,
                db=db,
                company_id=event.company_id,
                result_summary=f"already_{session.state.lower()}",
            )
            db.commit()
            return

        session.state = "EXPIRED"
        mark_processed(
            key=event.idempotency_key,
            consumer=_CONSUMER,
            event_id=event.event_id,
            db=db,
            company_id=event.company_id,
            result_summary="expired_ok",
        )
        db.commit()

        logger.info(
            "handle_booking_session_expired: sessão %s marcada EXPIRED",
            booking_session_id_str,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_booking_session_expired: erro session_id=%s event_id=%s",
            booking_session_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra todos os handlers de booking_session no EventBus global."""
    from app.infrastructure.event_bus import event_bus
    event_bus.register("booking_session.expired", handle_booking_session_expired)
    logger.info("booking_session_handlers: handlers registrados")
