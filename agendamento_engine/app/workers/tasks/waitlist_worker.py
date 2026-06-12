"""
Celery task da fila de espera — Sprint G.

waitlist_expire_entries_worker:
  Beat a cada 30 min — entries NOTIFIED com expires_at < now() → EXPIRED;
  o próximo elegível da fila é notificado (slot continua livre).
"""
import logging

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.waitlist_worker.waitlist_expire_entries_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def waitlist_expire_entries_worker(self):
    """Scan multi-tenant: expira notificações sem ação e passa a vez."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.modules.waitlist import service as waitlist_service
        expired = waitlist_service.expire_waitlist_entries(db)
        logger.info("waitlist_expire_entries: %d entradas expiradas", expired)
    except Exception:
        db.rollback()
        logger.exception("waitlist_expire_entries: erro attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
