"""
Celery tasks para expiração de reservas SOFT — Sprint 10.

expire_soft_reservations_scan:
  Beat periódico (a cada 5 min).
  Scan multi-tenant: encontra todas as SOFT ACTIVE com expires_at < now()
  e chama expire_soft_reservation para cada uma.

dispatch_soft_reservation_expired:
  Task unitária disparada por expire_soft_reservation (via .delay()).
  Publica o evento agenda.soft_reservation.expired no EventBus para que
  o handler cancele o appointment vinculado (se em DRAFT ou REQUESTED).

Separado do booking_session_worker — domínios distintos.
"""
import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.expire_reservations.expire_soft_reservations_scan",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def expire_soft_reservations_scan(self):
    """Scan periódico: expira SOFTs vencidas e emite evento para cada uma."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.reservation import Reservation
        now = datetime.now(timezone.utc)

        expired = (
            db.query(Reservation)
            .filter(
                Reservation.type == "SOFT",
                Reservation.status == "ACTIVE",
                Reservation.expires_at < now,
            )
            .limit(200)
            .all()
        )

        if not expired:
            logger.debug("expire_reservations: nenhuma SOFT expirada")
            return

        logger.info("expire_reservations: %d SOFTs expiradas encontradas", len(expired))

        from app.modules.agenda import reservation_service
        for r in expired:
            reservation_service.expire_soft_reservation(r.reservation_id, r.company_id, db)
        db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "expire_reservations: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.expire_reservations.dispatch_soft_reservation_expired",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
)
def dispatch_soft_reservation_expired(self, reservation_id_str: str, company_id_str: str):
    """
    Publica evento agenda.soft_reservation.expired no EventBus.
    Chamado por expire_soft_reservation após marcar status=EXPIRED.
    """
    from app.infrastructure.event_bus import DomainEvent, event_bus

    reservation_id = UUID(reservation_id_str)
    company_id = UUID(company_id_str)
    now = datetime.now(timezone.utc)

    event = DomainEvent(
        event_id=uuid.uuid4(),
        event_type="agenda.soft_reservation.expired",
        occurred_at=now,
        company_id=company_id,
        idempotency_key=f"agenda.soft_reservation.expired:{reservation_id}",
        actor={"type": "SYSTEM", "id": None},
        payload={
            "reservation_id": str(reservation_id),
            "company_id": str(company_id),
        },
    )
    event_bus.publish(event)
    logger.info(
        "dispatch_soft_reservation_expired: evento publicado reservation_id=%s",
        reservation_id_str,
    )
