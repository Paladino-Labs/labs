"""
Notificações transacionais de agendamento.

Responsabilidades:
  - Enviar confirmação de agendamento ao cliente (via CommunicationService)
  - Enviar confirmação de reagendamento ao cliente (via CommunicationService)

Contrato:
  - Todas as funções são fire-and-forget: erros são logados, nunca propagados.
    O fluxo de negócio não deve ser interrompido por falha de notificação.
  - Recebem db + Appointment já commitado e refreshado.
  - Convertem start_at de UTC para o fuso da empresa antes de formatar.

Sprint I:
  Chamadas diretas ao evolution_client foram removidas — todo envio passa por
  CommunicationService.dispatch (template + CommunicationLog).
  Feature flag TenantConfig.permission_overrides["use_communication_service"]
  funciona como kill-switch: default True (ausente = habilitado).
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.infrastructure.db.models import Appointment, Customer
from app.infrastructure.db.models.company_settings import CompanySettings

logger = logging.getLogger(__name__)


def _use_communication_service(db: Session, company_id) -> bool:
    """Kill-switch do CommunicationService. Flag ausente → True (default Sprint I)."""
    try:
        from app.infrastructure.db.models.tenant_config import TenantConfig
        config = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
        overrides = (config.permission_overrides or {}) if config else {}
        return bool(overrides.get("use_communication_service", True))
    except Exception:
        return True

_DEFAULT_TZ = "America/Sao_Paulo"

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _get_company_tz(db: Session, company_id) -> ZoneInfo:
    try:
        row = (
            db.query(CompanySettings.timezone)
            .filter(CompanySettings.company_id == company_id)
            .first()
        )
        tz_name = (row.timezone if row and row.timezone else _DEFAULT_TZ)
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo(_DEFAULT_TZ)


def _localize(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def _fmt_datetime(dt: datetime, tz: ZoneInfo) -> tuple[str, str]:
    """Retorna (data_legivel, hora) no fuso da empresa. Ex: ('5 de maio', '14:30')"""
    local = _localize(dt, tz)
    data  = f"{local.day} de {MONTHS_PT[local.month - 1]}"
    hora  = f"{local.hour:02d}:{local.minute:02d}"
    return data, hora


def send_booking_confirmation(
    db: Session, appointment: Appointment, manage_token: str | None = None
) -> None:
    """
    Envia confirmação de agendamento ao cliente via CommunicationService.
    Fire-and-forget: erros são apenas logados.
    """
    _notify_appointment(
        db, appointment, "appointment.confirmed", "send_booking_confirmation",
        manage_token=manage_token,
    )


def send_reschedule_confirmation(
    db: Session, appointment: Appointment, manage_token: str | None = None
) -> None:
    """
    Envia confirmação de reagendamento ao cliente via CommunicationService.
    Fire-and-forget: erros são apenas logados.
    """
    _notify_appointment(
        db, appointment, "appointment.confirmed", "send_reschedule_confirmation",
        manage_token=manage_token,
    )


def _notify_appointment(
    db: Session,
    appointment: Appointment,
    event_type: str,
    caller: str,
    manage_token: str | None = None,
) -> None:
    try:
        customer = db.query(Customer).filter(
            Customer.id == appointment.client_id
        ).first()
        if not customer or not customer.phone:
            logger.debug("%s: cliente sem phone appt_id=%s", caller, appointment.id)
            return

        if not _use_communication_service(db, appointment.company_id):
            logger.debug(
                "%s: use_communication_service desligado company_id=%s",
                caller, appointment.company_id,
            )
            return

        tz = _get_company_tz(db, appointment.company_id)
        _dispatch_via_comm_service(
            db, appointment, customer, event_type, "CLIENT", tz,
            manage_token=manage_token,
        )

        logger.info(
            "%s: dispatch enviado appt_id=%s phone=%s",
            caller, appointment.id, customer.phone,
        )
    except Exception:
        # Nunca propagar — notificação não deve derrubar o fluxo de negócio
        logger.exception("%s: falha ao enviar appt_id=%s", caller, appointment.id)


def _dispatch_via_comm_service(
    db: Session,
    appointment: Appointment,
    customer: Customer,
    event_type: str,
    recipient_type: str,
    tz: ZoneInfo,
    manage_token: str | None = None,
) -> None:
    """Dispatch via CommunicationService (fire-and-forget)."""
    try:
        from app.modules.appointments.manage_tokens import build_manage_url

        data, hora = _fmt_datetime(appointment.start_at, tz)
        svc_name = appointment.services[0].service_name if appointment.services else "serviço"
        prof_name = appointment.professional.name if appointment.professional else "profissional"
        manage_url = build_manage_url(manage_token) if manage_token else ""

        from app.modules.communication.service import communication_service
        communication_service.dispatch(
            event_type=event_type,
            company_id=appointment.company_id,
            context={
                "cliente_nome": customer.name,
                "horario": hora,
                "data": data,
                "servico": svc_name,
                "profissional": prof_name,
                "empresa_nome": "",
                "manage_url": manage_url,
                "recipient_phone": customer.phone,
            },
            recipient_id=customer.id,
            recipient_type=recipient_type,
            db=db,
        )
    except Exception:
        logger.exception(
            "_dispatch_via_comm_service: falha event=%s appt_id=%s",
            event_type, appointment.id,
        )
