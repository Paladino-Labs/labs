"""
Handler para operation.completed — Sprint 12.

Comportamento:
  - Recebe o evento operation.completed quando um agendamento é COMPLETED.
  - Chama CommissionEngine.calculate_commission (best-effort).
  - Falha não impacta a operação concluída.
  - Abre SessionLocal própria (não recebe db via EventBus).
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def handle_operation_completed(event) -> None:
    """Handler para operation.completed."""
    payload = event.payload
    appointment_id_str: str = payload.get("appointment_id")
    professional_id_str: str = payload.get("professional_id")
    service_id_str: str = payload.get("service_id")
    gross_amount_str: str = payload.get("gross_amount", "0")
    provider_fee_str: str = payload.get("provider_fee", "0")
    company_id_str: str = payload.get("company_id")

    if not professional_id_str or not company_id_str:
        logger.warning(
            "handle_operation_completed: payload incompleto — professional_id ou company_id ausente event_id=%s",
            event.event_id,
        )
        return

    db: Session = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        company_id = UUID(company_id_str)
        set_rls_context(db, company_id)

        from app.modules.commission import service as commission_service

        commission_service.calculate_commission(
            professional_id=UUID(professional_id_str),
            service_id=UUID(service_id_str) if service_id_str else None,
            gross_amount=Decimal(gross_amount_str),
            provider_fee=Decimal(provider_fee_str),
            operation_type="SERVICE_RENDERED",
            appointment_id=UUID(appointment_id_str) if appointment_id_str else None,
            company_id=company_id,
            db=db,
        )

        logger.info(
            "handle_operation_completed: comissão calculada appointment_id=%s professional_id=%s",
            appointment_id_str, professional_id_str,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_operation_completed: erro (best-effort) appointment_id=%s event_id=%s",
            appointment_id_str, event.event_id,
        )
    finally:
        db.close()


def register_handlers() -> None:
    """Registra o handler operation.completed no EventBus global."""
    from app.infrastructure.event_bus import event_bus
    event_bus.register("operation.completed", handle_operation_completed)
    logger.info("commission_handler: handler operation.completed registrado")
