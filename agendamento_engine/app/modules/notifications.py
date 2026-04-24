"""
Notificações transacionais de agendamento.

Responsabilidades:
  - Enviar confirmação de agendamento via WhatsApp ao cliente
  - Enviar confirmação de reagendamento via WhatsApp ao cliente

Contrato:
  - Todas as funções são fire-and-forget: erros são logados, nunca propagados.
    O fluxo de negócio não deve ser interrompido por falha de notificação.
  - Recebem db + Appointment já commitado e refreshado.
  - Buscam a conexão WhatsApp da empresa internamente.
  - Convertem start_at de UTC para o fuso da empresa antes de formatar.
"""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.infrastructure.db.models import Appointment, WhatsAppConnection, Customer
from app.infrastructure.db.models.company_settings import CompanySettings
from app.modules.whatsapp import evolution_client

logger = logging.getLogger(__name__)

_DEFAULT_TZ = "America/Sao_Paulo"

MONTHS_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def _get_whatsapp_conn(db: Session, company_id) -> "WhatsAppConnection | None":
    return db.query(WhatsAppConnection).filter(
        WhatsAppConnection.company_id == company_id,
        WhatsAppConnection.status == "CONNECTED",
    ).first()


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


def send_booking_confirmation(db: Session, appointment: Appointment) -> None:
    """
    Envia confirmação de agendamento ao cliente via WhatsApp.
    Fire-and-forget: erros são apenas logados.
    """
    try:
        customer = db.query(Customer).filter(
            Customer.id == appointment.client_id
        ).first()
        if not customer or not customer.phone:
            logger.debug(
                "send_booking_confirmation: cliente sem phone appt_id=%s", appointment.id
            )
            return

        conn = _get_whatsapp_conn(db, appointment.company_id)
        if not conn:
            logger.debug(
                "send_booking_confirmation: empresa sem WhatsApp conectado company_id=%s",
                appointment.company_id,
            )
            return

        tz          = _get_company_tz(db, appointment.company_id)
        data, hora  = _fmt_datetime(appointment.start_at, tz)
        first_name  = customer.name.split()[0]
        svc_name    = appointment.services[0].service_name if appointment.services else "serviço"
        prof_name   = appointment.professional.name if appointment.professional else "profissional"

        msg = (
            f"Olá, {first_name}! ✅\n\n"
            f"Seu agendamento foi confirmado:\n\n"
            f"✂️  *{svc_name}*\n"
            f"👤  {prof_name}\n"
            f"📅  {data} às {hora}\n\n"
            f"Te esperamos! Qualquer dúvida, é só responder aqui. 😊"
        )

        evolution_client.send_text(conn.instance_name, customer.phone, msg)

        logger.info(
            "send_booking_confirmation: enviado appt_id=%s phone=%s",
            appointment.id, customer.phone,
        )

    except Exception:
        # Nunca propagar — notificação não deve derrubar o fluxo de negócio
        logger.exception(
            "send_booking_confirmation: falha ao enviar appt_id=%s", appointment.id
        )


def send_reschedule_confirmation(db: Session, appointment: Appointment) -> None:
    """
    Envia confirmação de reagendamento ao cliente via WhatsApp.
    Fire-and-forget: erros são apenas logados.
    """
    try:
        customer = db.query(Customer).filter(
            Customer.id == appointment.client_id
        ).first()
        if not customer or not customer.phone:
            return

        conn = _get_whatsapp_conn(db, appointment.company_id)
        if not conn:
            return

        tz         = _get_company_tz(db, appointment.company_id)
        data, hora = _fmt_datetime(appointment.start_at, tz)
        first_name = customer.name.split()[0]
        svc_name   = appointment.services[0].service_name if appointment.services else "serviço"
        prof_name  = appointment.professional.name if appointment.professional else "profissional"

        msg = (
            f"Olá, {first_name}! 🔄\n\n"
            f"Seu agendamento foi remarcado:\n\n"
            f"✂️  *{svc_name}*\n"
            f"👤  {prof_name}\n"
            f"📅  {data} às {hora}\n\n"
            f"Qualquer dúvida, é só responder aqui. 😊"
        )

        evolution_client.send_text(conn.instance_name, customer.phone, msg)

        logger.info(
            "send_reschedule_confirmation: enviado appt_id=%s phone=%s",
            appointment.id, customer.phone,
        )

    except Exception:
        logger.exception(
            "send_reschedule_confirmation: falha ao enviar appt_id=%s", appointment.id
        )