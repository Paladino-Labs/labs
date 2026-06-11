"""
Celery task de expiração noturna de promoções e cupons — Sprint 16.

promotions_expiry_scanner:
  Beat diário às 00:05.
  Scan multi-tenant:
    Promotions ACTIVE com valid_until < now() → EXPIRED (promotion.expired)
    Coupons ACTIVE com expires_at < now()     → CANCELLED (coupon.expired)
  Idempotência: status já EXPIRED/CANCELLED não entra no scan → skip natural.
"""
import logging
import uuid
from datetime import datetime, timezone

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.workers.tasks.promotions_expiry.promotions_expiry_scanner",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def promotions_expiry_scanner(self):
    """Expira promoções e cancela cupons vencidos."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS

        from app.infrastructure.db.models.promotion import Coupon, Promotion
        from app.infrastructure.event_bus import DomainEvent, event_bus

        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        expired_promotions = (
            db.query(Promotion)
            .filter(
                Promotion.status == "ACTIVE",
                Promotion.valid_until != None,  # noqa: E711
                Promotion.valid_until < now,
            )
            .limit(500)
            .all()
        )
        for promo in expired_promotions:
            promo.status = "EXPIRED"
            promo.updated_at = now
            try:
                event_bus.publish(DomainEvent(
                    event_id=uuid.uuid4(),
                    event_type="promotion.expired",
                    occurred_at=now,
                    company_id=promo.company_id,
                    idempotency_key=f"promotion.expired:{promo.id}:{today}",
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "promotion_id": str(promo.id),
                        "company_id": str(promo.company_id),
                    },
                ))
            except Exception:
                logger.exception(
                    "promotions_expiry: erro ao publicar promotion.expired id=%s",
                    promo.id,
                )

        expired_coupons = (
            db.query(Coupon)
            .filter(
                Coupon.status == "ACTIVE",
                Coupon.expires_at != None,  # noqa: E711
                Coupon.expires_at < now,
            )
            .limit(500)
            .all()
        )
        for coupon in expired_coupons:
            coupon.status = "CANCELLED"
            try:
                event_bus.publish(DomainEvent(
                    event_id=uuid.uuid4(),
                    event_type="coupon.expired",
                    occurred_at=now,
                    company_id=coupon.company_id,
                    idempotency_key=f"coupon.expired:{coupon.id}:{today}",
                    actor={"type": "SYSTEM", "id": None},
                    payload={
                        "coupon_id": str(coupon.id),
                        "company_id": str(coupon.company_id),
                    },
                ))
            except Exception:
                logger.exception(
                    "promotions_expiry: erro ao publicar coupon.expired id=%s",
                    coupon.id,
                )

        if not expired_promotions and not expired_coupons:
            logger.debug("promotions_expiry: nada a expirar")
            return

        db.commit()
        logger.info(
            "promotions_expiry: %d promoções EXPIRED, %d cupons CANCELLED",
            len(expired_promotions), len(expired_coupons),
        )

    except Exception:
        db.rollback()
        logger.exception(
            "promotions_expiry: erro no scan attempt=%d", self.request.retries
        )
        raise
    finally:
        db.close()
