"""Handlers de comunicação registrados no EventBus — Sprint 9.

payment.confirmed:
  Best-effort — falha no handler NÃO impacta o pagamento confirmado.
  Chamado após commit de confirm(), nunca dentro da transação.
"""
import logging
from uuid import UUID

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_payment_confirmed_notification(event) -> None:
    """Envia notificação transacional ao cliente após pagamento confirmado.

    best-effort: exceções são capturadas e logadas; não propagadas.
    """
    try:
        payment_id = event.payload.get("payment_id")
        customer_id = event.payload.get("customer_id")
        company_id = event.company_id

        if not customer_id or not company_id:
            logger.debug(
                "handle_payment_confirmed_notification: payload incompleto, pulando event_id=%s",
                event.event_id,
            )
            return

        from app.modules.communication.service import communication_service

        db = SessionLocal()
        try:
            communication_service.dispatch(
                db=db,
                company_id=company_id,
                recipient_id=UUID(customer_id),
                recipient_type="CLIENT",
                event_type="payment.confirmed",
                context={
                    "payment_id": str(payment_id),
                    "amount": event.payload.get("amount", ""),
                },
            )
        except Exception:
            logger.exception(
                "handle_payment_confirmed_notification: dispatch falhou payment_id=%s", payment_id
            )
        finally:
            db.close()

    except Exception:
        logger.exception(
            "handle_payment_confirmed_notification: falha inesperada event_id=%s", event.event_id
        )


def register_handlers() -> None:
    """Registra handlers de comunicação no EventBus global."""
    event_bus.register("payment.confirmed", handle_payment_confirmed_notification)
    logger.info("communication_handlers: handlers registrados")
