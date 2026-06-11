"""Handler de promoções — Sprint 16.

payment.confirmed (5º listener):
  Extrai payment_id, company_id, coupon_code do payload e chama
  promotion_service.effectuate(). Best-effort — falha não impacta o
  pagamento confirmado. Idempotência dentro do effectuate
  (DiscountApplications existentes para o payment → no-op).

payment.refunded:
  promotion_service.revert_for_refund() — preenche reverted_at em
  CouponRedemption/DiscountApplication e aplica coupon_reopen_policy.
"""
import logging
from uuid import UUID

from app.core.db_rls import set_rls_context
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_payment_confirmed_promotion(event) -> None:
    """Efetiva promoções/cupons quando pagamento é confirmado."""
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
        if not payment:
            return

        coupon_code = event.payload.get("coupon_code") or payment.coupon_code
        customer_id = payment.customer_id

        from app.modules.promotions import service as promotion_service
        promotion_service.effectuate(
            db=db,
            company_id=company_id,
            payment_id=payment.payment_id,
            gross_amount=payment.gross_catalog_amount,
            coupon_code=coupon_code,
            customer_id=customer_id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_confirmed_promotion: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def handle_payment_refunded_promotion(event) -> None:
    """Reverte redenções e aplicações quando pagamento é estornado."""
    payment_id_str = event.payload.get("payment_id")
    company_id = event.company_id

    if not payment_id_str or not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.modules.promotions import service as promotion_service
        promotion_service.revert_for_refund(
            db=db,
            company_id=company_id,
            payment_id=UUID(payment_id_str),
            reason="payment.refunded",
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_refunded_promotion: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de promoção no EventBus global."""
    event_bus.register("payment.confirmed", handle_payment_confirmed_promotion)
    event_bus.register("payment.refunded", handle_payment_refunded_promotion)
    logger.info("promotion_payment_handler: handlers registrados")
