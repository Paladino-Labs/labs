"""
Celery tasks de NPS — Sprint G.

nps_send_pending_worker:
  Beat a cada 15 min — envia NpsSurveys PENDING com scheduled_for <= now()
  via CommunicationService (consent e quiet hours dentro do dispatch).

nps_expire_surveys_worker:
  Beat diário às 01:00 — SENT com expires_at < now() → EXPIRED.
"""
import logging

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.nps_worker.nps_send_pending_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def nps_send_pending_worker(self):
    """Scan multi-tenant: envia pesquisas NPS pendentes."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.modules.nps import service as nps_service
        sent = nps_service.send_pending_surveys(db)
        logger.info("nps_send_pending: %d pesquisas enviadas", sent)
    except Exception:
        db.rollback()
        logger.exception("nps_send_pending: erro attempt=%d", self.request.retries)
        raise
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="app.workers.tasks.nps_worker.nps_expire_surveys_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def nps_expire_surveys_worker(self):
    """Scan diário: expira pesquisas SENT sem resposta após 48h."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.modules.nps import service as nps_service
        expired = nps_service.expire_surveys(db)
        logger.info("nps_expire_surveys: %d pesquisas expiradas", expired)
    except Exception:
        db.rollback()
        logger.exception("nps_expire_surveys: erro attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
