"""Handlers do estado ESCOLHENDO_HORARIO."""
import uuid as uuidlib
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import label_date
from app.modules.booking.engine import booking_engine
from app.core.config import settings

STATE_ESCOLHENDO_HORARIO = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA    = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO        = "CONFIRMANDO"


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    send_escolher_data,
    send_confirmacao_resumo,
) -> None:
    ctx      = dict(session.context or {})
    svc_id   = UUID(ctx["service_id"])
    prof_raw = ctx.get("professional_id")
    date_str = ctx.get("selected_date")
    prof_id_val = UUID(prof_raw) if prof_raw else None

    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
        slots = booking_engine.list_available_slots(
            db, company_id, prof_id_val, svc_id, target_date,
            limit=settings.BOT_MAX_SLOTS_DISPLAYED,
        )
    else:
        slots = booking_engine.list_next_available_slots(
            db, company_id, prof_id_val, svc_id,
            days=7, limit=settings.BOT_MAX_SLOTS_DISPLAYED,
        )

    any_prof = (prof_raw is None)

    if not slots:
        ctx["last_list"] = [
            {"row_id": "opt_outra_data", "payload": "outra_data"},
            {"row_id": "opt_menu",       "payload": "opt_menu"},
        ]
        session.context = ctx
        session.state   = STATE_ESCOLHENDO_HORARIO
        sender.send_buttons(
            instance, whatsapp_id, messages.SEM_HORARIOS,
            [
                {"buttonId": "opt_outra_data",
                 "buttonText": {"displayText": "📅 Escolher outra data"}},
                {"buttonId": "opt_menu",
                 "buttonText": {"displayText": "🏠 Menu principal"}},
            ],
        )
        return

    rows, last_list = [], []
    for s in slots:
        row_id = f"{s.start_at.isoformat()}|{s.professional_id}"
        rows.append({
            "rowId":       row_id,
            "title":       s.start_at.strftime("%H:%M"),
            "description": s.professional_name if any_prof else "",
        })
        last_list.append({"row_id": row_id, "payload": row_id,
                          "professional_name": s.professional_name})

    rows.append({"rowId": "opt_outra_data", "title": "📅 Escolher outra data", "description": ""})
    last_list.append({"row_id": "opt_outra_data", "payload": "outra_data"})

    ctx["last_list"] = last_list
    session.context  = ctx
    session.state    = STATE_ESCOLHENDO_HORARIO

    prof_label = ctx.get("professional_name", "")
    sender.send_list(
        instance, whatsapp_id,
        "🕐 Horários disponíveis",
        messages.escolha_horario(ctx["service_name"], prof_label),
        rows,
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    send_escolher_data,
    send_confirmacao_resumo,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    if payload == "outra_data":
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if "|" not in payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    try:
        start_str, prof_id_str = payload.split("|", 1)
    except ValueError:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["slot_start_at"] = start_str

    if not ctx.get("professional_id"):
        ctx["professional_id"] = prof_id_str
        # professional_name já armazenado em last_list pelo start()
        selected = next(
            (e for e in ctx.get("last_list", []) if e.get("payload") == payload),
            {},
        )
        if selected.get("professional_name"):
            ctx["professional_name"] = selected["professional_name"]

    ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
    session.context = ctx
    session.state   = STATE_CONFIRMANDO
    send_confirmacao_resumo(instance, whatsapp_id, ctx)