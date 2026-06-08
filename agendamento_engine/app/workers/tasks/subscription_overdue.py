"""
Celery task para gerenciar inadimplência de assinaturas — Sprint 15.

subscription_overdue_worker:
  Beat diário às 08:00.
  - ACTIVE com Payment PENDING criado há > 7 dias → OVERDUE
  - OVERDUE há > 30 dias (overdue_since < now - 30d) → SUSPENDED
"""
import logging
from datetime import datetime, timedelta, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.core.db_rls import set_rls_context

logger = logging.getLogger(__name__)

GRACE_PERIOD_DAYS = 7
SUSPEND_THRESHOLD_DAYS = 30


@celery_app.task(
    bind=True,
    name="app.workers.tasks.subscription_overdue.subscription_overdue_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def subscription_overdue_worker(self):
    """Gerencia inadimplência: ACTIVE→OVERDUE após 7d; OVERDUE→SUSPENDED após 30d."""
    db = SessionLocal()
    try:
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.subscription import CustomerSubscription
        from app.infrastructure.db.models.payment import Payment

        now = datetime.now(timezone.utc)
        overdue_cutoff = now - timedelta(days=GRACE_PERIOD_DAYS)
        suspend_cutoff = now - timedelta(days=SUSPEND_THRESHOLD_DAYS)

        # ACTIVE com Payment PENDING criado há > grace_period_days → OVERDUE
        active_subscriptions = (
            db.query(CustomerSubscription)
            .filter(CustomerSubscription.status == "ACTIVE")
            .all()
        )

        marked_overdue = 0
        for sub in active_subscriptions:
            old_pending = (
                db.query(Payment)
                .filter(
                    Payment.subscription_id == sub.subscription_id,
                    Payment.status == "PENDING",
                    Payment.created_at <= overdue_cutoff,
                )
                .first()
            )
            if old_pending:
                sub.status = "OVERDUE"
                sub.overdue_since = now
                db.flush()
                marked_overdue += 1
                logger.info(
                    "subscription_overdue: ACTIVE→OVERDUE subscription_id=%s",
                    sub.subscription_id,
                )

        # OVERDUE há > auto_cancel_threshold_days → SUSPENDED
        overdue_subscriptions = (
            db.query(CustomerSubscription)
            .filter(
                CustomerSubscription.status == "OVERDUE",
                CustomerSubscription.overdue_since <= suspend_cutoff,
            )
            .all()
        )

        marked_suspended = 0
        for sub in overdue_subscriptions:
            sub.status = "SUSPENDED"
            db.flush()
            marked_suspended += 1
            logger.info(
                "subscription_overdue: OVERDUE→SUSPENDED subscription_id=%s",
                sub.subscription_id,
            )

        db.commit()
        logger.info(
            "subscription_overdue: %d OVERDUE, %d SUSPENDED",
            marked_overdue, marked_suspended,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "subscription_overdue: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()
