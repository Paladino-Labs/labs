"""
Worker de lembretes de agendamento via WhatsApp.

Executa a cada 10 minutos. Em cada ciclo, busca agendamentos
que estejam dentro da janela de tempo de cada lembrete e envia
mensagens via Evolution API.

Janelas de detecção (±10min ao redor do marco):
  - 24h: start_at BETWEEN (now + 23h50m) AND (now + 24h10m)
  - 2h:  start_at BETWEEN (now + 1h50m) AND (now + 2h10m)

Idempotência:
  - reminder_24h_sent / reminder_2h_sent são setados após envio bem-sucedido.
  - Em caso de crash após o envio mas antes do SET, o worker pode re-enviar
    na próxima execução — máximo 1 duplicata por agendamento no pior caso.
  - FOR UPDATE SKIP LOCKED garante que deploys multi-processo não enviem
    o mesmo lembrete em paralelo.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models import Appointment, WhatsAppConnection, Customer
from app.modules.whatsapp import evolution_client
from app.core.config import settings

logger = logging.getLogger(__name__)

_INTERVAL_SECONDS = 10 * 60   # 10 minutos
_WINDOW_MINUTES   = 10         # janela de ±10 min ao redor do marco


async def run_reminder_worker() -> None:
    """Loop infinito. Registrado no startup do FastAPI."""
    logger.info("reminder_worker: iniciado (intervalo=%ds)", _INTERVAL_SECONDS)
    while True:
        try:
            await _send_reminders_once()
        except Exception:
            logger.exception("reminder_worker: erro inesperado")
        await asyncio.sleep(_INTERVAL_SECONDS)


async def _send_reminders_once() -> None:
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _send_reminders_sync)


def _send_reminders_sync() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        _process_24h(db, now)
        _process_2h(db, now)
    except Exception:
        logger.exception("reminder_worker: erro inesperado no ciclo")
    finally:
        db.close()


def _process_24h(db: Session, now: datetime) -> None:
    """Envia lembretes de 24h para agendamentos na janela correta."""
    advance = timedelta(hours=settings.BOT_REMINDER_ADVANCE_HOURS_FIRST)
    window  = timedelta(minutes=_WINDOW_MINUTES)
    low  = now + advance - window
    high = now + advance + window

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.start_at >= low,
            Appointment.start_at <= high,
            Appointment.status == "SCHEDULED",
            Appointment.reminder_24h_sent == False,
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    for appt in appointments:
        _send_reminder(db, appt, kind="24h")


def _process_2h(db: Session, now: datetime) -> None:
    """Envia lembretes de 2h para agendamentos na janela correta."""
    advance = timedelta(hours=settings.BOT_REMINDER_ADVANCE_HOURS_SECOND)
    window  = timedelta(minutes=_WINDOW_MINUTES)
    low  = now + advance - window
    high = now + advance + window

    appointments = (
        db.query(Appointment)
        .filter(
            Appointment.start_at >= low,
            Appointment.start_at <= high,
            Appointment.status == "SCHEDULED",
            Appointment.reminder_2h_sent == False,
        )
        .with_for_update(skip_locked=True)
        .all()
    )

    for appt in appointments:
        _send_reminder(db, appt, kind="2h")


def _send_reminder(db: Session, appt: Appointment, kind: str) -> None:
    """
    Envia o lembrete para o cliente do agendamento.
    Marca a flag de enviado apenas após sucesso no envio.
    """
    try:
        # Busca cliente para obter o número WhatsApp
        customer = db.query(Customer).filter(Customer.id == appt.client_id).first()
        if not customer or not customer.phone:
            logger.warning("reminder_worker: cliente sem phone appt_id=%s", appt.id)
            return

        # Busca instância WhatsApp da empresa
        conn = db.query(WhatsAppConnection).filter(
            WhatsAppConnection.company_id == appt.company_id,
            WhatsAppConnection.status == "CONNECTED",
        ).first()
        if not conn:
            logger.debug(
                "reminder_worker: empresa sem WhatsApp conectado company_id=%s",
                appt.company_id,
            )
            return

        service_name = appt.services[0].service_name if appt.services else "serviço"
        prof_name    = appt.professional.name if appt.professional else "profissional"
        hora         = appt.start_at.strftime("%H:%M")
        data         = appt.start_at.strftime("%d/%m")

        if kind == "24h":
            msg = (
                f"Olá, {customer.name}! 👋\n\n"
                f"Lembrete: você tem *{service_name}* com *{prof_name}* "
                f"amanhã, {data} às {hora}. 💈\n\n"
                f"Responda _Ver agendamentos_ para gerenciar."
            )
        else:  # 2h
            msg = (
                f"Olá, {customer.name}! 😊\n\n"
                f"Seu *{service_name}* começa em 2 horas, às {hora}. "
                f"Te esperamos! 💈"
            )

        evolution_client.send_text(conn.instance_name, customer.phone, msg)

        # Marca como enviado somente após o envio bem-sucedido
        if kind == "24h":
            appt.reminder_24h_sent = True
        else:
            appt.reminder_2h_sent = True
        db.commit()

        logger.info(
            "reminder_worker: lembrete %s enviado appt_id=%s phone=%s",
            kind, appt.id, customer.phone,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "reminder_worker: falha ao enviar lembrete %s appt_id=%s",
            kind, appt.id,
        )
