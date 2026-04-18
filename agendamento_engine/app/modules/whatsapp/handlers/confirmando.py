"""Handlers do estado CONFIRMANDO — resumo e criação do agendamento."""
import logging
import uuid as uuidlib
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.booking.engine import booking_engine
from app.modules.booking.schemas import BookingIntent
from app.modules.booking.exceptions import SlotUnavailableError
from app.core.config import settings

logger = logging.getLogger(__name__)

STATE_CONFIRMANDO = "CONFIRMANDO"

_CONFIRMANDO_LIST = [
    {"row_id": "opt_confirmar",       "payload": "opt_confirmar",
     "title": "✅ Confirmar"},
    {"row_id": "opt_alterar_horario", "payload": "opt_alterar_horario",
     "title": "🕐 Alterar horário"},
    {"row_id": "opt_cancelar",        "payload": "opt_cancelar",
     "title": "❌ Cancelar"},
]


def send_resumo(instance: str, whatsapp_id: str, ctx: dict) -> None:
    slot_dt    = datetime.fromisoformat(ctx["slot_start_at"])
    date_label = slot_dt.strftime("%d/%m/%Y")
    time_label = slot_dt.strftime("%H:%M")
    prof_label = ctx.get("professional_name") or "—"

    text = messages.confirmacao_resumo(
        ctx.get("service_name", "—"), prof_label, date_label, time_label
    )
    sender.send_buttons(
        instance, whatsapp_id, text,
        [
            {"buttonId": "opt_confirmar",
             "buttonText": {"displayText": "✅ Confirmar"}},
            {"buttonId": "opt_alterar_horario",
             "buttonText": {"displayText": "🕐 Alterar horário"}},
            {"buttonId": "opt_cancelar",
             "buttonText": {"displayText": "❌ Cancelar"}},
        ],
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_horario,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, _CONFIRMANDO_LIST)

    if payload == "opt_alterar_horario":
        ctx = dict(ctx)
        ctx.pop("slot_start_at", None)
        ctx.pop("selected_date", None)
        session.context = ctx
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "opt_cancelar":
        nome = first_name(ctx.get("customer_name", ""))
        reset_session(session)
        sender.send_text(instance, whatsapp_id, messages.cancelamento_pelo_usuario(nome))
        return

    if payload != "opt_confirmar":
        send_resumo(instance, whatsapp_id, ctx)
        return

    # ── Criar agendamento ──────────────────────────────────────────────────────
    start_at    = datetime.fromisoformat(ctx["slot_start_at"])
    idem_key    = ctx.get("booking_idempotency_key") or str(uuidlib.uuid4())
    prof_id_raw = ctx.get("professional_id")
    customer_id = ctx.get("customer_id")

    if not prof_id_raw or not customer_id:
        logger.error("CONFIRMANDO: dados incompletos ctx=%s whatsapp_id=%s", ctx, whatsapp_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_DADOS_INCOMPLETOS)
        reset_session(session)
        return

    intent = BookingIntent(
        company_id=company_id,
        customer_id=UUID(customer_id),
        professional_id=UUID(prof_id_raw),
        service_id=UUID(ctx["service_id"]),
        start_at=start_at,
        idempotency_key=idem_key,
    )
    try:
        booking_engine.confirm(db, company_id, intent)
    except SlotUnavailableError:
        sender.send_text(instance, whatsapp_id, messages.HORARIO_OCUPADO_CONFIRMANDO)
        ctx = dict(ctx)
        ctx.pop("slot_start_at", None)
        ctx.pop("selected_date", None)
        session.context = ctx
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
    except Exception:
        logger.exception("booking_engine.confirm failed whatsapp_id=%s", whatsapp_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_CONFIRMAR_AGENDAMENTO)
        return

    nome       = first_name(ctx.get("customer_name", ""))
    slot_label = start_at.strftime("%d/%m às %H:%M")
    sender.send_text(
        instance, whatsapp_id,
        messages.agendamento_confirmado(
            nome,
            ctx.get("service_name", ""),
            ctx.get("professional_name", ""),
            slot_label,
            settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
        ),
    )
    reset_session(session)