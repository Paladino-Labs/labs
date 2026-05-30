"""
Worker de expiração de booking_sessions — Sprint 4.

Scan periódico (Celery Beat, a cada 5 min) identifica sessões vencidas
e publica evento booking_session.expired no EventBus para cada uma.

Por que é tolerante sem outbox: se o processo cair após publicar e antes
do handler executar, o próximo scan republica porque a sessão continua
vencida e não-EXPIRED — idempotência vem do scan periódico.

ATENÇÃO: cobre APENAS booking_sessions (checkout web/whatsapp/admin).
         bot_sessions são gerenciadas pelo session_cleanup_worker.
         Não unificar — domínios distintos.
"""
import logging
import uuid
from datetime import datetime, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models.booking_session import BookingSession

logger = logging.getLogger(__name__)

_TERMINAL_STATES = {"CONFIRMED", "EXPIRED", "CANCELLED", "ERROR"}


@celery_app.task(
    bind=True,
    name="app.workers.booking_session_worker.scan_expired_booking_sessions",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def scan_expired_booking_sessions(self):
    """Escaneia booking_sessions vencidas e publica evento para cada uma."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS
        now = datetime.now(timezone.utc)
        expired_sessions = (
            db.query(BookingSession.id, BookingSession.company_id)
            .filter(
                BookingSession.expires_at < now,
                BookingSession.state.notin_(list(_TERMINAL_STATES)),
            )
            .limit(200)
            .all()
        )

        if not expired_sessions:
            logger.debug("booking_session_worker: nenhuma sessão expirada")
            return

        logger.info("booking_session_worker: %d sessões expiradas encontradas", len(expired_sessions))

        from app.infrastructure.event_bus import event_bus, DomainEvent
        for session_id, company_id in expired_sessions:
            event = DomainEvent(
                event_id=uuid.uuid4(),
                event_type="booking_session.expired",
                occurred_at=now,
                company_id=company_id,
                idempotency_key=f"booking_session.expired:{session_id}",
                actor={"type": "SYSTEM", "id": None},
                payload={"booking_session_id": str(session_id)},
            )
            event_bus.publish(event)

    except Exception:
        db.rollback()
        logger.exception("booking_session_worker: erro no scan attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
