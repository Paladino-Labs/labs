"""Celery task de recomputação de classificações CRM — Sprint H.

crm_recompute_worker:
  Beat diário às 03:00 (fora do horário de pico).
  Scan multi-tenant: para cada customer ativo recalcula métricas e
  classifica; insere nova linha em customer_classifications quando a
  classificação muda ou a última recomputação tem mais de 24h
  (append-only — histórico preservado). Commit em lote a cada 100.
  Aceita company_id opcional para forçar um único tenant (teste/manual).
"""
import logging
from typing import Optional

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.crm_recompute.crm_recompute_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def crm_recompute_worker(self, company_id: Optional[str] = None):
    """Recomputa classificações CRM de todos os tenants (ou de um só)."""
    db = SessionLocal()
    try:
        from uuid import UUID

        from app.core.db_rls import set_rls_context
        from app.modules.crm.service import recompute_all_classifications

        target = UUID(company_id) if company_id else None
        # scan multi-tenant — bypass RLS; tenant específico → contexto setado
        set_rls_context(db, target)

        inserted = recompute_all_classifications(db, company_id=target)
        logger.info("crm_recompute: %d classificações inseridas", inserted)

    except Exception:
        db.rollback()
        logger.exception(
            "crm_recompute: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()
