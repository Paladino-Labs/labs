"""
Celery task para renovação de assinaturas — Sprint 15.

subscription_renewal_worker:
  Beat diário às 06:00.
  Scan multi-tenant: encontra assinaturas ACTIVE com next_billing_at <= now()
  e cria um Payment PENDING para cada uma (se ainda não existe um PENDING).
  Avança next_billing_at += cycle_days após criar o pagamento.

Idempotência: não cria novo Payment se já existe Payment PENDING para a subscription.
"""
import logging
from datetime import datetime, timedelta, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.core.db_rls import set_rls_context

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.subscription_renewal.subscription_renewal_worker",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def subscription_renewal_worker(self):
    """Cria pagamentos de renovação para assinaturas ACTIVE com next_billing_at vencida."""
    db = SessionLocal()
    try:
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
        from app.infrastructure.db.models.payment import Payment

        now = datetime.now(timezone.utc)

        subscriptions = (
            db.query(CustomerSubscription)
            .filter(
                CustomerSubscription.status == "ACTIVE",
                CustomerSubscription.next_billing_at <= now,
            )
            .limit(200)
            .all()
        )

        if not subscriptions:
            logger.debug("subscription_renewal: nenhuma assinatura para renovar")
            return

        logger.info("subscription_renewal: %d assinaturas para renovar", len(subscriptions))

        renewed = 0
        for sub in subscriptions:
            # Idempotência: verificar se já existe Payment PENDING para esta subscription
            existing_pending = (
                db.query(Payment)
                .filter(
                    Payment.subscription_id == sub.subscription_id,
                    Payment.status == "PENDING",
                )
                .first()
            )
            if existing_pending:
                logger.debug(
                    "subscription_renewal: payment PENDING já existe subscription_id=%s",
                    sub.subscription_id,
                )
                continue

            plan = db.query(SubscriptionPlan).filter(
                SubscriptionPlan.plan_id == sub.plan_id
            ).first()
            if not plan:
                logger.warning("subscription_renewal: plano não encontrado plan_id=%s", sub.plan_id)
                continue

            try:
                _create_renewal_payment(db, sub, plan)
                # Avança next_billing_at
                sub.next_billing_at = sub.next_billing_at + timedelta(days=plan.cycle_days)
                db.flush()
                renewed += 1
            except Exception:
                logger.exception(
                    "subscription_renewal: erro ao criar payment subscription_id=%s",
                    sub.subscription_id,
                )
                db.rollback()
                # Re-query para continuar processando outras subscriptions
                db = SessionLocal()
                set_rls_context(db, None)

        db.commit()
        logger.info("subscription_renewal: %d pagamentos criados", renewed)

    except Exception:
        db.rollback()
        logger.exception(
            "subscription_renewal: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()


def _create_renewal_payment(db, sub, plan):
    """Cria Payment PENDING para renovação de assinatura (sem provider externo)."""
    import uuid
    from decimal import Decimal
    from app.infrastructure.db.models.payment import Payment
    from app.infrastructure.db.models.account import Account

    # Resolve conta CAIXA da empresa
    account = db.query(Account).filter(
        Account.company_id == sub.company_id,
        Account.is_default_inflow == True,
    ).first()
    if not account:
        logger.warning(
            "subscription_renewal: empresa sem conta CAIXA company_id=%s", sub.company_id
        )
        return

    payment = Payment(
        payment_id=uuid.uuid4(),
        company_id=sub.company_id,
        customer_id=sub.customer_id,
        subscription_id=sub.subscription_id,
        gross_catalog_amount=Decimal(str(plan.price)),
        discount_amount=Decimal("0"),
        net_charged_amount=Decimal(str(plan.price)),
        provider_fee=Decimal("0"),
        payment_method="PIX",
        provider="asaas",
        target_account_id=account.account_id,
        status="PENDING",
    )
    db.add(payment)
    db.flush()
    logger.info(
        "subscription_renewal: payment criado payment_id=%s subscription_id=%s",
        payment.payment_id, sub.subscription_id,
    )
