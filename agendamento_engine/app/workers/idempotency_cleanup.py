"""
Worker de limpeza de processed_idempotency_keys — Sprint 4.

Roda diariamente às 03:00 (Celery Beat).
Remove keys com processed_at > 30 dias para evitar crescimento ilimitado da tabela.
"""
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_RETENTION_DAYS = 30


@celery_app.task(
    bind=True,
    name="app.workers.idempotency_cleanup.cleanup_old_keys",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def cleanup_old_keys(self):
    """Remove processed_idempotency_keys com mais de 30 dias."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # limpeza de plataforma — bypass RLS
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RETENTION_DAYS)
        result = db.execute(
            text("DELETE FROM processed_idempotency_keys WHERE processed_at < :cutoff"),
            {"cutoff": cutoff},
        )
        db.commit()
        deleted = result.rowcount
        if deleted > 0:
            logger.info("idempotency_cleanup: %d keys removidas (cutoff=%s)", deleted, cutoff.date())
        else:
            logger.debug("idempotency_cleanup: nenhuma key antiga encontrada")
    except Exception:
        db.rollback()
        logger.exception("idempotency_cleanup: erro attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
