"""Handler do estado REAGENDANDO."""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.appointments.polices import PolicyViolationError
from app.modules.booking.engine import booking_engine
from app.modules.booking.exceptions import SlotUnavailableError

logger = logging.getLogger(__name__)


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    send_escolher_data,
    start_escolhendo_horario,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "outra_data":
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if "|" in payload:
        start_str, _ = payload.split("|", 1)
        new_start = datetime.fromisoformat(start_str)
    else:
        new_start = datetime.fromisoformat(payload)

    appt_id = UUID(ctx["managing_appointment_id"])
    try:
        booking_engine.reschedule(db, company_id, appt_id, new_start)
        nome       = first_name(ctx.get("customer_name", ""))
        slot_label = new_start.strftime("%d/%m às %H:%M")
        sender.send_text(instance, whatsapp_id,
                         messages.reagendamento_confirmado(nome, slot_label))
    except PolicyViolationError as e:
        sender.send_text(instance, whatsapp_id, f"⚠️ {e.detail}")
    except SlotUnavailableError:
        sender.send_text(instance, whatsapp_id, messages.HORARIO_OCUPADO_REAGENDANDO)
        ctx = dict(ctx)
        ctx.pop("slot_start_at", None)
        ctx.pop("selected_date", None)
        session.context = ctx
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
    except Exception:
        logger.exception("booking_engine.reschedule failed appt_id=%s", appt_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_REAGENDAR_AGENDAMENTO)

    reset_session(session)