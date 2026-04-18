"""Handlers do estado CANCELANDO."""
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.polices import PolicyViolationError, check_cancellation_policy
from app.modules.booking.engine import booking_engine
from app.modules.booking.exceptions import BookingNotFoundError
from app.core.config import settings

logger = logging.getLogger(__name__)


def start(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
    start_gerenciando_agendamento,
) -> None:
    ctx         = session.context or {}
    appt_id_str = ctx.get("managing_appointment_id")
    if not appt_id_str:
        reset_session(session)
        return

    try:
        appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(appt_id_str))
    except Exception:
        reset_session(session)
        return

    allowed, msg = check_cancellation_policy(
        start_at=appt.start_at,
        now=datetime.now(timezone.utc),
        min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
    )
    slot_label = appt.start_at.strftime("%d/%m às %H:%M")

    if not allowed:
        sender.send_text(instance, whatsapp_id, messages.cancelamento_fora_prazo(msg))
        start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)
        return

    ctx = dict(ctx)
    ctx["last_list"] = [
        {"row_id": "opt_confirmar_cancel",   "payload": "confirmar_cancel",
         "title": "✅ Sim, cancelar"},
        {"row_id": "opt_voltar_gerenciando", "payload": "voltar_gerenciando",
         "title": "← Não, voltar"},
    ]
    session.context = ctx
    sender.send_buttons(
        instance, whatsapp_id,
        messages.confirmacao_cancelamento(slot_label),
        [
            {"buttonId": "opt_confirmar_cancel",
             "buttonText": {"displayText": "✅ Sim, cancelar"}},
            {"buttonId": "opt_voltar_gerenciando",
             "buttonText": {"displayText": "← Não, voltar"}},
        ],
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_gerenciando_agendamento,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "voltar_gerenciando":
        appt_id_str = ctx.get("managing_appointment_id", "")
        try:
            appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(appt_id_str))
            start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)
        except Exception:
            reset_session(session)
        return

    if payload == "confirmar_cancel":
        appt_id_str = ctx.get("managing_appointment_id")
        if not appt_id_str:
            reset_session(session)
            return
        nome = first_name(ctx.get("customer_name", ""))
        try:
            booking_engine.cancel(
                db, company_id, UUID(appt_id_str),
                reason="Cancelado via WhatsApp",
            )
            sender.send_text(instance, whatsapp_id, messages.cancelamento_confirmado(nome))
        except PolicyViolationError as e:
            sender.send_text(instance, whatsapp_id, f"⚠️ {e.detail}")
        except BookingNotFoundError:
            sender.send_text(instance, whatsapp_id, "❌ Agendamento não encontrado.")
        except Exception:
            logger.exception("booking_engine.cancel failed id=%s", appt_id_str)
            sender.send_text(instance, whatsapp_id, messages.ERRO_CANCELAR_AGENDAMENTO)
        reset_session(session)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO)