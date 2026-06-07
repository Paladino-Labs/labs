"""
Celery task para expiração de CustomerCredits vencidos — Sprint 13.

customer_credit_expiry_worker:
  Beat diário às 02:30.
  Scan multi-tenant: encontra todos os ACTIVE com expires_at < now()
  e muda status para EXPIRED.
"""
import logging
from datetime import datetime, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.customer_credit_expiry.customer_credit_expiry_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def customer_credit_expiry_worker(self):
    """Scan periódico: expira créditos ACTIVE com expires_at no passado."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.customer_credit import CustomerCredit
        from app.infrastructure.event_bus import DomainEvent, event_bus
        import uuid

        now = datetime.now(timezone.utc)

        expired = (
            db.query(CustomerCredit)
            .filter(
                CustomerCredit.status == "ACTIVE",
                CustomerCredit.expires_at != None,
                CustomerCredit.expires_at < now,
            )
            .limit(500)
            .all()
        )

        if not expired:
            logger.debug("customer_credit_expiry: nenhum crédito expirado")
            return

        logger.info("customer_credit_expiry: %d créditos expirados encontrados", len(expired))

        for credit in expired:
            credit.status = "EXPIRED"
            try:
                event = DomainEvent(
                    event_id=uuid.uuid4(),
                    event_type="customer_credit.expired",
                    occurred_at=now,
                    company_id=credit.company_id,
                    idempotency_key=f"customer_credit.expired:{credit.credit_id}",
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "credit_id": str(credit.credit_id),
                        "customer_id": str(credit.customer_id),
                        "company_id": str(credit.company_id),
                    },
                )
                event_bus.publish(event)
            except Exception:
                logger.exception(
                    "customer_credit_expiry: erro ao publicar evento credit_id=%s",
                    credit.credit_id,
                )

        db.commit()
        logger.info("customer_credit_expiry: %d créditos expirados com sucesso", len(expired))

    except Exception:
        db.rollback()
        logger.exception(
            "customer_credit_expiry: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()
