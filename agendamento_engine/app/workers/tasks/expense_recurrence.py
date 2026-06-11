"""
Celery task de geração de recorrência de despesas — Sprint 18.

expense_recurrence_worker:
  Beat diário às 06:00.
  Scan multi-tenant: despesas PAGA com recurrence_rule e sem próxima
  instância PENDENTE encadeada (parent_expense_id) → cria a próxima.
  Idempotência: generate_next_instance verifica existência antes de criar.
"""
import logging

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.expense_recurrence.expense_recurrence_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def expense_recurrence_worker(self):
    """Scan diário: gera próxima instância para despesas PAGA recorrentes."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.expense import Expense
        from app.modules.expenses.service import generate_next_instance

        paid_recurring = (
            db.query(Expense)
            .filter(
                Expense.status == "PAGA",
                Expense.recurrence_rule.isnot(None),
            )
            .limit(500)
            .all()
        )

        if not paid_recurring:
            logger.debug("expense_recurrence: nenhuma despesa recorrente paga")
            return

        created = 0
        for expense in paid_recurring:
            try:
                next_expense = generate_next_instance(expense, db)
                if next_expense is not None:
                    created += 1
            except Exception:
                db.rollback()
                logger.exception(
                    "expense_recurrence: erro ao gerar próxima instância expense_id=%s",
                    expense.id,
                )

        logger.info("expense_recurrence: %d instâncias criadas", created)

    except Exception:
        db.rollback()
        logger.exception("expense_recurrence: erro no scan attempt=%d", self.request.retries)
        raise
    finally:
        db.close()
