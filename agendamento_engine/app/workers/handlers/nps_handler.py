"""Handler de NPS — Sprint G.

operation.completed:
  Extrai appointment_id, company_id, customer_id e chama
  nps_service.schedule_nps_survey(). Best-effort — falha não impacta a
  conclusão do atendimento. Idempotência dupla:
    - processed_idempotency_keys (key "nps.schedule:{appointment_id}")
    - UNIQUE(appointment_id) em nps_surveys (defesa no banco)
"""
import logging
from uuid import UUID

from app.core.db_rls import set_rls_context
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.event_bus import event_bus

logger = logging.getLogger(__name__)

_CONSUMER = "nps_schedule_handler"


def handle_operation_completed_nps(event) -> None:
    """Agenda pesquisa NPS quando uma operação é concluída."""
    appointment_id_str = event.payload.get("appointment_id")
    customer_id_str = event.payload.get("customer_id")
    company_id = event.company_id

    if not appointment_id_str or not company_id:
        return

    db = SessionLocal()
    try:
        set_rls_context(db, company_id)

        from app.core.idempotency import is_processed, mark_processed

        key = f"nps.schedule:{appointment_id_str}"
        if is_processed(key, _CONSUMER, db):
            return

        appointment_id = UUID(appointment_id_str)

        # Payloads pré-Sprint G não trazem customer_id — resolve pelo appointment
        if customer_id_str:
            customer_id = UUID(customer_id_str)
        else:
            from app.infrastructure.db.models import Appointment
            appointment = (
                db.query(Appointment)
                .filter(
                    Appointment.id == appointment_id,
                    Appointment.company_id == company_id,
                )
                .first()
            )
            if appointment is None:
                return
            customer_id = appointment.client_id

        from app.modules.nps import service as nps_service
        nps_service.schedule_nps_survey(
            db, appointment_id=appointment_id,
            company_id=company_id, customer_id=customer_id,
        )

        mark_processed(key, _CONSUMER, event.event_id, db, company_id=company_id)
        db.commit()

    except Exception:
        db.rollback()
        logger.exception(
            "handle_operation_completed_nps: erro (best-effort) appointment_id=%s event_id=%s",
            appointment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra handlers de NPS no EventBus global."""
    event_bus.register("operation.completed", handle_operation_completed_nps)
    logger.info("nps_handler: handlers registrados")
