"""
Celery task de aviso de vencimento de contas a pagar — Sprint 17.

payable_due_worker:
  Beat diário às 07:30 (mesmo horário do expense_due_soon).
  Scan multi-tenant: Payables OPEN/PARTIALLY_PAID com due_date entre hoje
  e hoje+3 dias → publica payable.due_soon
  (idempotência: "payable.due_soon:{id}:{n}_days").
  Payables com due_date < hoje → publica payable.overdue
  (idempotência por data: "payable.overdue:{id}:{date}").
"""
import logging
from datetime import datetime, timedelta, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_CONSUMER = "payable_due_publisher"
_DUE_SOON_WINDOW_DAYS = 3


@celery_app.task(
    bind=True,
    name="app.workers.tasks.payable_due.payable_due_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def payable_due_worker(self):
    """Scan diário: publica payable.due_soon e payable.overdue."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.core.idempotency import is_processed, mark_processed
        from app.infrastructure.db.models.payable import Payable
        from app.infrastructure.event_bus import DomainEvent, event_bus
        import uuid

        now = datetime.now(timezone.utc)
        today = now.date()
        window_end = today + timedelta(days=_DUE_SOON_WINDOW_DAYS)

        open_payables = (
            db.query(Payable)
            .filter(
                Payable.status.in_(("OPEN", "PARTIALLY_PAID")),
                Payable.due_date.isnot(None),
                Payable.due_date <= window_end,
            )
            .limit(500)
            .all()
        )

        if not open_payables:
            logger.debug("payable_due: nenhuma conta na janela")
            return

        published = 0
        for payable in open_payables:
            if payable.due_date < today:
                event_type = "payable.overdue"
                key = f"payable.overdue:{payable.id}:{today.isoformat()}"
            else:
                days_until_due = (payable.due_date - today).days
                event_type = "payable.due_soon"
                key = f"payable.due_soon:{payable.id}:{days_until_due}_days"

            if is_processed(key, _CONSUMER, db):
                continue

            event_id = uuid.uuid4()
            try:
                event_bus.publish(DomainEvent(
                    event_id=event_id,
                    event_type=event_type,
                    occurred_at=now,
                    company_id=payable.company_id,
                    idempotency_key=key,
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "payable_id": str(payable.id),
                        "company_id": str(payable.company_id),
                        "description": payable.description,
                        "total_amount": str(payable.total_amount),
                        "paid_amount": str(payable.paid_amount),
                        "status": payable.status,
                        "due_date": payable.due_date.isoformat(),
                    },
                ))
                mark_processed(key, _CONSUMER, event_id, db, company_id=payable.company_id)
                published += 1
            except Exception:
                logger.exception(
                    "payable_due: erro ao publicar %s payable_id=%s",
                    event_type, payable.id,
                )

        db.commit()
        logger.info("payable_due: %d eventos publicados", published)

    except Exception:
        db.rollback()
        logger.exception("payable_due: erro no scan attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
