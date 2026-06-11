"""
Celery task de aviso de vencimento de despesas — Sprint 18.

expense_due_soon_worker:
  Beat diário às 07:30 (padrão de horário da visão).
  Scan multi-tenant: despesas PENDENTE com due_date entre hoje e hoje+3 dias
  → publica expense.due_soon (idempotente via processed_idempotency_keys).
  Despesas PENDENTE com due_date < hoje → publica expense.overdue
  (idempotente por data: expense.overdue:{id}:{date}).
"""
import logging
from datetime import datetime, timedelta, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)

_CONSUMER = "expense_due_soon_publisher"
_DUE_SOON_WINDOW_DAYS = 3


@celery_app.task(
    bind=True,
    name="app.workers.tasks.expense_due_soon.expense_due_soon_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def expense_due_soon_worker(self):
    """Scan diário: publica expense.due_soon e expense.overdue para PENDENTE."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.core.idempotency import is_processed, mark_processed
        from app.infrastructure.db.models.expense import Expense
        from app.infrastructure.event_bus import DomainEvent, event_bus
        import uuid

        now = datetime.now(timezone.utc)
        today = now.date()
        window_end = today + timedelta(days=_DUE_SOON_WINDOW_DAYS)

        pending = (
            db.query(Expense)
            .filter(
                Expense.status == "PENDENTE",
                Expense.due_date <= window_end,
            )
            .limit(500)
            .all()
        )

        if not pending:
            logger.debug("expense_due_soon: nenhuma despesa na janela")
            return

        published = 0
        for expense in pending:
            if expense.due_date < today:
                event_type = "expense.overdue"
                key = f"expense.overdue:{expense.id}:{today.isoformat()}"
            else:
                days_until_due = (expense.due_date - today).days
                event_type = "expense.due_soon"
                key = f"expense.due_soon:{expense.id}:{days_until_due}_days"

            if is_processed(key, _CONSUMER, db):
                continue

            event_id = uuid.uuid4()
            try:
                event_bus.publish(DomainEvent(
                    event_id=event_id,
                    event_type=event_type,
                    occurred_at=now,
                    company_id=expense.company_id,
                    idempotency_key=key,
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "expense_id": str(expense.id),
                        "company_id": str(expense.company_id),
                        "description": expense.description,
                        "amount": str(expense.amount),
                        "due_date": expense.due_date.isoformat(),
                    },
                ))
                mark_processed(key, _CONSUMER, event_id, db, company_id=expense.company_id)
                published += 1
            except Exception:
                logger.exception(
                    "expense_due_soon: erro ao publicar %s expense_id=%s",
                    event_type, expense.id,
                )

        db.commit()
        logger.info("expense_due_soon: %d eventos publicados", published)

    except Exception:
        db.rollback()
        logger.exception("expense_due_soon: erro no scan attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
