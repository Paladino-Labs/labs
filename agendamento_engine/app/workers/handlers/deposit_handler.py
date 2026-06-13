"""
Handler de sinal/depósito — Sprint 25.

payment.confirmed → promove a Reservation SOFT do slot do appointment para FIRME.
Best-effort: no-op se o pagamento não tem appointment ou não há SOFT ativa no slot.
Não duplica efeito — promote_to_firme só age sobre SOFT ACTIVE (idempotente por estado).
"""
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def handle_payment_confirmed_deposit(event) -> None:
    payload = event.payload
    payment_id_str: str = payload.get("payment_id")
    company_id_str: str = payload.get("company_id")

    if not payment_id_str or not company_id_str:
        return

    db: Session = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        company_id = UUID(company_id_str)
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
        if not payment or not payment.appointment_id:
            return  # sem agendamento → nada a promover

        from app.modules.payments import deposit_service

        firme = deposit_service.promote_reservation_for_appointment(
            appointment_id=payment.appointment_id,
            company_id=company_id,
            db=db,
        )
        if firme is not None:
            db.commit()
            logger.info(
                "handle_payment_confirmed_deposit: SOFT→FIRME promovida "
                "appointment_id=%s payment_id=%s",
                payment.appointment_id, payment_id_str,
            )
    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_confirmed_deposit: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    from app.infrastructure.event_bus import event_bus
    event_bus.register("payment.confirmed", handle_payment_confirmed_deposit)
    logger.info("deposit_handler: handler payment.confirmed registrado")
