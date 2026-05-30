"""
Handler para appointment.reminder_due — Sprint 5.

Idempotency key: appointment.reminder_due:{appointment_id}:{interval}  (Padrão B)
Consumer: "appointment_reminder"

Sprint 5: handler usa CommunicationService quando flag use_communication_service está ativa.
Enquanto a flag está desligada (padrão), reminder_worker Celery continua enviando
diretamente via Evolution API (coexistência).

O evento NÃO passa pelo EventBus (fluxo crítico) — é publicado diretamente
pelo Celery Beat / reminder_worker via envio direto. Este handler é registrado
no EventBus para fluxos tolerantes e logging.
"""
import logging
from uuid import UUID

logger = logging.getLogger(__name__)

_CONSUMER = "appointment_reminder"


def handle_appointment_reminder_due(event) -> None:
    """
    Handler para appointment.reminder_due via EventBus.
    Delega ao CommunicationService quando flag habilitada.
    """
    from app.infrastructure.db.session import SessionLocal
    from app.infrastructure.db.models.tenant_config import TenantConfig

    appointment_id = event.payload.get("appointment_id")
    interval = event.payload.get("interval", "unknown")
    company_id = event.company_id

    logger.info(
        "appointment_reminder_handler: reminder_due recebido appt_id=%s interval=%s event_id=%s",
        appointment_id, interval, event.event_id,
    )

    if not appointment_id or not company_id:
        return

    db = SessionLocal()
    try:
        config = db.query(TenantConfig).filter(
            TenantConfig.company_id == company_id
        ).first()
        overrides = (config.permission_overrides or {}) if config else {}
        if not overrides.get("use_communication_service"):
            return

        from app.infrastructure.db.models import Appointment, Customer
        from app.infrastructure.db.models.company_settings import CompanySettings
        from app.modules.communication.service import communication_service
        from zoneinfo import ZoneInfo

        appt = db.query(Appointment).filter(
            Appointment.id == UUID(str(appointment_id)),
            Appointment.company_id == company_id,
        ).first()
        if not appt:
            return

        customer = db.query(Customer).filter(Customer.id == appt.client_id).first()
        if not customer or not customer.phone:
            return

        tz_row = db.query(CompanySettings.timezone).filter(
            CompanySettings.company_id == company_id
        ).first()
        tz = ZoneInfo(tz_row.timezone if tz_row and tz_row.timezone else "America/Sao_Paulo")
        start_local = appt.start_at.astimezone(tz) if appt.start_at.tzinfo else appt.start_at

        template_event = f"appointment.reminder_{interval}" if interval != "unknown" else "appointment.reminder_due"

        communication_service.dispatch(
            event_type=template_event,
            company_id=company_id,
            context={
                "cliente_nome": customer.name,
                "horario": start_local.strftime("%H:%M"),
                "data": start_local.strftime("%d/%m"),
                "servico": appt.services[0].service_name if appt.services else "serviço",
                "profissional": appt.professional.name if appt.professional else "profissional",
                "empresa_nome": "",
                "recipient_phone": customer.phone,
            },
            recipient_id=customer.id,
            recipient_type="CLIENT",
            db=db,
        )
    except Exception:
        logger.exception(
            "appointment_reminder_handler: falha appt_id=%s interval=%s",
            appointment_id, interval,
        )
    finally:
        db.close()


def register_handlers() -> None:
    from app.infrastructure.event_bus import event_bus
    event_bus.register("appointment.reminder_due", handle_appointment_reminder_due)
    logger.info("appointment_reminder_handler: handler registrado")
