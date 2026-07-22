"""Handlers de fila de espera — Sprint G.

appointment.cancelled / appointment.rescheduled:
  Slot liberado → notify_waitlist para os escopos SERVICE (cada service_id
  do appointment) e PROFESSIONAL. Best-effort.

stock.entry_recorded:
  Reabastecimento → notify_waitlist scope PRODUCT para cada product_id do
  payload (payloads pré-Sprint G sem product_ids → resolve via SupplierOrder
  não é possível sem itens persistidos por produto; nesse caso, no-op).
"""
import logging
from uuid import UUID

from app.core.db_rls import set_rls_context
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)


def handle_appointment_cancelled_waitlist(event) -> None:
    """Slot liberado por cancelamento/remarcação → notifica a fila."""
    company_id = event.company_id
    if not company_id:
        return

    professional_id_str = event.payload.get("professional_id")
    service_ids = event.payload.get("service_ids") or []
    single_service = event.payload.get("service_id")
    if single_service and single_service not in service_ids:
        service_ids = list(service_ids) + [single_service]

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)
        from app.modules.waitlist import service as waitlist_service

        for service_id_str in service_ids:
            waitlist_service.notify_waitlist(
                db, company_id, "SERVICE",
                service_id=UUID(service_id_str),
                reason=event.event_type,
            )

        if professional_id_str:
            waitlist_service.notify_waitlist(
                db, company_id, "PROFESSIONAL",
                professional_id=UUID(professional_id_str),
                reason=event.event_type,
            )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_appointment_cancelled_waitlist: erro (best-effort) event_id=%s",
            event.event_id,
        )
    finally:
        db.close()


def handle_stock_entry_recorded_waitlist(event) -> None:
    """Reabastecimento de produto → notifica a fila de cada produto."""
    company_id = event.company_id
    product_ids = event.payload.get("product_ids") or []
    if not company_id or not product_ids:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)
        from app.modules.waitlist import service as waitlist_service

        for product_id_str in product_ids:
            waitlist_service.notify_waitlist(
                db, company_id, "PRODUCT",
                product_id=UUID(product_id_str),
                reason="stock_replenished",
            )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_stock_entry_recorded_waitlist: erro (best-effort) event_id=%s",
            event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de fila de espera no EventBus global."""
    event_bus.register("appointment.cancelled", handle_appointment_cancelled_waitlist)
    event_bus.register("appointment.rescheduled", handle_appointment_cancelled_waitlist)
    event_bus.register("stock.entry_recorded", handle_stock_entry_recorded_waitlist)
    logger.info("waitlist_handler: handlers registrados")
