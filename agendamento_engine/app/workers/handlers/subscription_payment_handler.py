"""Handler para eventos de assinaturas — Sprint 15.

payment.confirmed:
  Busca Payment por payment_id e verifica subscription_id.
  Se subscription_id preenchido: renova CustomerCredit + Entry ASSINATURA_RENOVACAO.
  best-effort — falha não impacta o pagamento confirmado.
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from app.infrastructure.db.session import SessionLocal
from app.core.db_rls import set_rls_context
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_payment_confirmed_subscription(event) -> None:
    """Renova CustomerCredit se payment está vinculado a uma CustomerSubscription."""
    payment_id_str = event.payload.get("payment_id")
    company_id = event.company_id

    if not payment_id_str or not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.infrastructure.db.models.payment import Payment
        payment = (
            db.query(Payment)
            .filter(
                Payment.payment_id == UUID(payment_id_str),
                Payment.company_id == company_id,
            )
            .first()
        )

        if not payment or not payment.subscription_id:
            return

        from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
        subscription = db.query(CustomerSubscription).filter(
            CustomerSubscription.subscription_id == payment.subscription_id,
            CustomerSubscription.company_id == company_id,
        ).first()

        if not subscription:
            logger.warning(
                "handle_payment_confirmed_subscription: subscription não encontrada subscription_id=%s",
                payment.subscription_id,
            )
            return

        plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.plan_id == subscription.plan_id,
        ).first()

        if not plan:
            logger.warning(
                "handle_payment_confirmed_subscription: plano não encontrado plan_id=%s",
                subscription.plan_id,
            )
            return

        now = datetime.now(timezone.utc)

        # Cria CustomerCredit para o ciclo renovado
        from app.infrastructure.db.models.customer_credit import CustomerCredit
        expires_at = None
        if not plan.rollover_enabled:
            expires_at = now + timedelta(days=plan.cycle_days)

        credit = CustomerCredit(
            credit_id=uuid.uuid4(),
            company_id=company_id,
            customer_id=subscription.customer_id,
            entitlement_type="SUBSCRIPTION",
            source_id=subscription.subscription_id,
            total_cotas=plan.cotas_per_cycle,
            remaining_cotas=plan.cotas_per_cycle,
            status="ACTIVE",
            granted_at=now,
            expires_at=expires_at,
        )
        db.add(credit)
        db.flush()

        # Entry RECEITA ASSINATURA_RENOVACAO via FinancialCoreEngine
        from app.modules.financial_core import service as financial_core
        financial_core.handle_subscription_renewed(
            subscription_id=subscription.subscription_id,
            plan_price=Decimal(str(plan.price)),
            target_account_id=payment.target_account_id,
            company_id=company_id,
            db=db,
        )

        # Se estava OVERDUE: volta para ACTIVE após pagamento confirmado
        if subscription.status == "OVERDUE":
            subscription.status = "ACTIVE"
            subscription.overdue_since = None
            db.flush()

        db.commit()

        # Emite subscription.renewed (best-effort)
        try:
            from app.infrastructure.event_bus import DomainEvent
            event_bus.publish(DomainEvent(
                event_id=uuid.uuid4(),
                event_type="subscription.renewed",
                occurred_at=now,
                company_id=company_id,
                idempotency_key=f"subscription.renewed:{subscription.subscription_id}:{payment_id_str}",
                actor={"type": "SYSTEM", "id": None},
                payload={
                    "subscription_id": str(subscription.subscription_id),
                    "payment_id": payment_id_str,
                    "credit_id": str(credit.credit_id),
                },
            ))
        except Exception:
            pass

        logger.info(
            "handle_payment_confirmed_subscription: crédito renovado subscription_id=%s credit_id=%s",
            subscription.subscription_id, credit.credit_id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_confirmed_subscription: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de assinaturas no EventBus global."""
    event_bus.register("payment.confirmed", handle_payment_confirmed_subscription)
    logger.info("subscription_handler: handlers registrados")
