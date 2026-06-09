"""
Handler de comissão — Sprint 12 / corrigido em payment.confirmed.

Comportamento:
  - payment.confirmed → handle_payment_confirmed_commission
    Lê provider_fee real do Payment (não "0" hardcoded do evento operation.completed).
  - handle_operation_completed mantido mas NÃO registrado.
    Stage 0 (barbershop): todo serviço renderizado tem pagamento associado;
    provider_fee em operation.completed é sempre "0" (hardcoded em transitions.py).
"""
import logging
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal

logger = logging.getLogger(__name__)


def handle_payment_confirmed_commission(event) -> None:
    """Calcula comissão quando pagamento é confirmado, usando provider_fee real do Payment."""
    payload = event.payload
    payment_id_str: str = payload.get("payment_id")
    company_id_str: str = payload.get("company_id")

    if not payment_id_str or not company_id_str:
        logger.warning(
            "handle_payment_confirmed_commission: payload incompleto event_id=%s",
            event.event_id,
        )
        return

    db: Session = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        company_id = UUID(company_id_str)
        set_rls_context(db, company_id)

        from app.infrastructure.db.models.payment import Payment
        from app.infrastructure.db.models.appointment import Appointment

        payment = db.query(Payment).filter(
            Payment.payment_id == UUID(payment_id_str),
            Payment.company_id == company_id,
        ).first()

        if not payment or not payment.appointment_id:
            return  # pagamento sem agendamento não gera comissão

        appointment = db.query(Appointment).filter(
            Appointment.id == payment.appointment_id,
            Appointment.company_id == company_id,
        ).first()

        if not appointment or not appointment.professional_id:
            return  # agendamento sem profissional não gera comissão

        from app.infrastructure.db.models.commission import Commission

        existing = db.query(Commission).filter(
            Commission.appointment_id == appointment.id,
            Commission.company_id == company_id,
            Commission.status != "REVERSED",
        ).first()
        if existing:
            logger.info(
                "handle_payment_confirmed_commission: comissão já existe "
                "para appointment_id=%s, ignorando",
                appointment.id,
            )
            return

        service_id = None
        if appointment.services:
            service_id = appointment.services[0].service_id

        from app.modules.commission import service as commission_service

        commission_service.calculate_commission(
            professional_id=appointment.professional_id,
            service_id=service_id,
            gross_amount=Decimal(str(payment.gross_catalog_amount)),
            provider_fee=Decimal(str(payment.provider_fee)),
            operation_type="SERVICE_RENDERED",
            appointment_id=appointment.id,
            company_id=company_id,
            db=db,
        )

        logger.info(
            "handle_payment_confirmed_commission: comissão calculada payment_id=%s appointment_id=%s",
            payment_id_str, appointment.id,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "handle_payment_confirmed_commission: erro (best-effort) payment_id=%s event_id=%s",
            payment_id_str, event.event_id,
        )
    finally:
        db.close()


def handle_operation_completed(event) -> None:
    """Handler para operation.completed — mantido mas NÃO registrado.

    provider_fee neste evento é sempre "0" (hardcoded em transitions.py).
    Comissão calculada em handle_payment_confirmed_commission com provider_fee real.
    """
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
    """Registra handler de comissão no EventBus global.

    payment.confirmed: provider_fee real do Payment (corrige AFTER_FEES).
    operation.completed: NÃO registrado — provider_fee sempre "0" nesse evento.
    """
    from app.infrastructure.event_bus import event_bus
    event_bus.register("payment.confirmed", handle_payment_confirmed_commission)
    logger.info("commission_handler: handler payment.confirmed registrado")
