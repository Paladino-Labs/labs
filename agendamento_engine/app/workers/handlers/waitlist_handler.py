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

from app.core.celery_db_context import celery_db_session
from app.core.db_rls import set_rls_context
from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus
from app.workers.communication_worker import _push_dead_letter

logger = logging.getLogger(__name__)


def handle_appointment_cancelled_waitlist(event) -> None:
    """Slot liberado por cancelamento/remarcação → ENFILEIRA a notificação da
    fila (S2.1).

    Antes o handler abria sessão e chamava notify_waitlist inline — como o
    EventBus.publish é síncrono in-process, o httpx da Evolution entrava na
    latência do request de cancel/reschedule sem o service anunciar. Agora só
    extrai escalares do payload e enfileira; o envio roda no worker.
    """
    company_id = event.company_id
    if not company_id:
        return

    professional_id_str = event.payload.get("professional_id")
    service_ids = event.payload.get("service_ids") or []
    single_service = event.payload.get("service_id")
    if single_service and single_service not in service_ids:
        service_ids = list(service_ids) + [single_service]

    for service_id_str in service_ids:
        _enqueue_waitlist_notify(company_id, "SERVICE", service_id_str, event.event_type)

    if professional_id_str:
        _enqueue_waitlist_notify(company_id, "PROFESSIONAL", professional_id_str, event.event_type)


def _enqueue_waitlist_notify(company_id, scope_type: str, target_id, reason: str) -> None:
    """Enfileira notify_waitlist_slot_available. Best-effort: broker fora do ar
    é logado e engolido — não derruba o cancel/reschedule que publicou o evento."""
    try:
        notify_waitlist_slot_available.apply_async(
            args=[str(company_id), scope_type, str(target_id), reason],
            retry=False,
        )
    except Exception:
        logger.exception(
            "waitlist enqueue falhou scope=%s target=%s company=%s",
            scope_type, target_id, company_id,
        )


@celery_app.task(
    bind=True,
    name="app.workers.handlers.waitlist_handler.notify_waitlist_slot_available",
    max_retries=3,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
)
def notify_waitlist_slot_available(self, company_id: str, scope_type: str, target_id: str, reason: str):
    """Notifica o 1º elegível da fila para um escopo — fora do request (S2.1).

    O envio httpx da Evolution acontece aqui, não no cancel/reschedule. Reusa
    o notify_waitlist existente (notifica só o 1º elegível; não reserva slot).
    """
    from app.modules.waitlist import service as waitlist_service

    scope_kwargs = {
        "SERVICE": "service_id",
        "PROFESSIONAL": "professional_id",
        "PRODUCT": "product_id",
    }
    kwargs = {}
    key = scope_kwargs.get(scope_type)
    if key:
        kwargs[key] = UUID(target_id)

    try:
        with celery_db_session(company_id) as db:
            waitlist_service.notify_waitlist(
                db, UUID(company_id), scope_type, reason=reason, **kwargs,
            )
    except Exception as exc:
        logger.exception(
            "notify_waitlist_slot_available: erro scope=%s target=%s attempt=%d",
            scope_type, target_id, self.request.retries,
        )
        if self.request.retries >= self.max_retries:
            _push_dead_letter(
                "notify_waitlist_slot_available",
                str(self.request.id), self.request.retries, exc,
            )
        raise


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
