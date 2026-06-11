"""
Worker de lembretes de agendamento via WhatsApp — Celery task.

Migrado de asyncio loop para Celery Beat no Sprint 4.
Agendado via beat_schedule: a cada 10 minutos.

Estratégia de coexistência: durante a transição, asyncio workers ainda
podem estar ativos em paralelo. Idempotência via reminder_24h_sent /
reminder_2h_sent garante zero duplicatas — quem chegar primeiro marca
o flag e o outro pula.

Após 24h de coexistência sem erros: remover asyncio.create_task do lifespan.
"""
import logging
import redis as redis_client
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.celery_app import celery_app
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.db.models import Appointment, Customer
from app.infrastructure.db.models.company_settings import CompanySettings
from app.core.config import settings

logger = logging.getLogger(__name__)

_WINDOW_MINUTES = 10
_DEFAULT_TZ = "America/Sao_Paulo"
_DEAD_LETTER_KEY = "dead_letter:send_reminders"


def _company_tz(db: Session, company_id) -> ZoneInfo:
    try:
        row = (
            db.query(CompanySettings.timezone)
            .filter(CompanySettings.company_id == company_id)
            .first()
        )
        tz_name = row.timezone if row and row.timezone else _DEFAULT_TZ
        return ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, Exception):
        return ZoneInfo(_DEFAULT_TZ)


def _localize(dt: datetime, tz: ZoneInfo) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


@celery_app.task(
    bind=True,
    name="app.workers.reminder_worker.send_reminders",
    max_retries=5,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=3600,
    retry_jitter=True,
)
def send_reminders(self):
    """Busca e envia lembretes de 24h e 2h para agendamentos na janela."""
    db = SessionLocal()
    try:
        from app.core.db_rls import set_rls_context
        set_rls_context(db, None)  # scan multi-tenant — bypass RLS
        now = datetime.now(timezone.utc)
        _process_24h(db, now)
        _process_2h(db, now)
    except Exception as exc:
        db.rollback()
        logger.exception("reminder_worker: erro no ciclo attempt=%d", self.request.retries)
        if self.request.retries >= self.max_retries:
            _push_dead_letter(self, exc)
        raise
    finally:
        db.close()


def _push_dead_letter(task, exc: Exception) -> None:
    try:
        r = redis_client.from_url(settings.REDIS_URL)
        r.rpush(
            _DEAD_LETTER_KEY,
            f"task_id={task.request.id} retries={task.request.retries} error={exc!r}",
        )
        logger.error(
            "reminder_worker: dead-letter após %d tentativas task_id=%s",
            task.request.retries, task.request.id,
        )
    except Exception:
        logger.exception("reminder_worker: falha ao gravar dead-letter")


def _process_24h(db: Session, now: datetime) -> None:
    advance = timedelta(hours=settings.BOT_REMINDER_ADVANCE_HOURS_FIRST)
    window = timedelta(minutes=_WINDOW_MINUTES)
    low = now + advance - window
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
    advance = timedelta(hours=settings.BOT_REMINDER_ADVANCE_HOURS_SECOND)
    window = timedelta(minutes=_WINDOW_MINUTES)
    low = now + advance - window
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
    """Envia lembrete via CommunicationService (Sprint I — sem chamada direta).

    O dispatch grava CommunicationLog (SENT/SCHEDULED/FAILED/SKIPPED_*).
    O flag reminder_*_sent só é marcado quando o dispatch NÃO falhou —
    FAILED deixa o flag em False para retry no próximo scan da janela.
    """
    try:
        customer = db.query(Customer).filter(Customer.id == appt.client_id).first()
        if not customer or not customer.phone:
            logger.warning("reminder_worker: cliente sem phone appt_id=%s", appt.id)
            return

        tz = _company_tz(db, appt.company_id)
        start_local = _localize(appt.start_at, tz)
        service_name = appt.services[0].service_name if appt.services else "serviço"
        prof_name = appt.professional.name if appt.professional else "profissional"

        from app.modules.communication.service import communication_service
        log_entry = communication_service.dispatch(
            event_type=f"appointment.reminder_{kind}",
            company_id=appt.company_id,
            context={
                "cliente_nome": customer.name,
                "horario": start_local.strftime("%H:%M"),
                "data": start_local.strftime("%d/%m"),
                "servico": service_name,
                "profissional": prof_name,
                "empresa_nome": "",
                "recipient_phone": customer.phone,
            },
            recipient_id=customer.id,
            recipient_type="CLIENT",
            db=db,
        )

        if log_entry.status == "FAILED":
            logger.warning(
                "reminder_worker: dispatch FAILED lembrete %s appt_id=%s — retry no próximo scan",
                kind, appt.id,
            )
            return

        if kind == "24h":
            appt.reminder_24h_sent = True
        else:
            appt.reminder_2h_sent = True
        db.commit()

        logger.info(
            "reminder_worker: lembrete %s despachado status=%s appt_id=%s phone=%s",
            kind, log_entry.status, appt.id, customer.phone,
        )

    except Exception:
        db.rollback()
        logger.exception(
            "reminder_worker: falha ao enviar lembrete %s appt_id=%s",
            kind, appt.id,
        )
        raise


# --- Compatibilidade asyncio (mantida durante coexistência, removida ao fim do Sprint 4) ---
import asyncio as _asyncio


async def run_reminder_worker() -> None:
    """Loop asyncio legado. Mantido durante coexistência com Celery. Ver plano-fase1-v3.md."""
    import logging as _logging
    _log = _logging.getLogger(__name__)
    _log.info("reminder_worker: asyncio loop iniciado (coexistência com Celery)")
    while True:
        try:
            loop = _asyncio.get_event_loop()
            await loop.run_in_executor(None, _send_reminders_sync_compat)
        except Exception:
            _log.exception("reminder_worker (asyncio): erro inesperado")
        await _asyncio.sleep(10 * 60)


def _send_reminders_sync_compat() -> None:
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        _process_24h(db, now)
        _process_2h(db, now)
    except Exception:
        logger.exception("reminder_worker (asyncio compat): erro inesperado no ciclo")
    finally:
        db.close()
