"""
Celery task de alerta de estoque baixo — Sprint 17.

stock_alert_worker:
  Beat diário às 07:00.
  Scan multi-tenant: produtos ativos com stock_min_alert configurado e
  stock <= stock_min_alert → publica stock.low_alert.
  Idempotente por dia: "stock.low_alert:{product_id}:{date}".
"""
import logging
from datetime import datetime, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_CONSUMER = "stock_alert_publisher"


@celery_app.task(
    bind=True,
    name="app.workers.tasks.stock_alert.stock_alert_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def stock_alert_worker(self):
    """Scan diário: publica stock.low_alert para produtos com estoque baixo."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.core.idempotency import is_processed, mark_processed
        from app.infrastructure.db.models.product import Product
        from app.infrastructure.event_bus import DomainEvent, event_bus
        import uuid

        now = datetime.now(timezone.utc)
        today = now.date()

        low_stock = (
            db.query(Product)
            .filter(
                Product.active == True,  # noqa: E712
                Product.stock_min_alert.isnot(None),
                Product.stock <= Product.stock_min_alert,
            )
            .limit(500)
            .all()
        )

        if not low_stock:
            logger.debug("stock_alert: nenhum produto abaixo do mínimo")
            return

        published = 0
        for product in low_stock:
            key = f"stock.low_alert:{product.id}:{today.isoformat()}"
            if is_processed(key, _CONSUMER, db):
                continue

            event_id = uuid.uuid4()
            try:
                event_bus.publish(DomainEvent(
                    event_id=event_id,
                    event_type="stock.low_alert",
                    occurred_at=now,
                    company_id=product.company_id,
                    idempotency_key=key,
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "product_id": str(product.id),
                        "company_id": str(product.company_id),
                        "name": product.name,
                        "stock": product.stock,
                        "stock_min_alert": str(product.stock_min_alert),
                    },
                ))
                mark_processed(key, _CONSUMER, event_id, db, company_id=product.company_id)
                published += 1
            except Exception:
                logger.exception(
                    "stock_alert: erro ao publicar stock.low_alert product_id=%s",
                    product.id,
                )

        db.commit()
        logger.info("stock_alert: %d eventos publicados", published)

    except Exception:
        db.rollback()
        logger.exception("stock_alert: erro no scan attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
