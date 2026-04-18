"""Handlers do estado ESCOLHENDO_SERVICO."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.booking.engine import booking_engine

STATE_ESCOLHENDO_SERVICO = "ESCOLHENDO_SERVICO"


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    options = booking_engine.list_services(db, company_id)
    ctx     = dict(session.context or {})

    if not options:
        ctx["last_list"] = [
            {"row_id": "opt_menu",   "payload": "opt_menu"},
            {"row_id": "opt_humano", "payload": "opt_humano"},
        ]
        session.context = ctx
        sender.send_buttons(
            instance, whatsapp_id, messages.SEM_SERVICOS,
            [
                {"buttonId": "opt_menu",   "buttonText": {"displayText": "🏠 Menu principal"}},
                {"buttonId": "opt_humano", "buttonText": {"displayText": "💬 Falar com atendente"}},
            ],
        )
        return

    rows = [
        {"rowId": o.row_key, "title": o.name,
         "description": f"R$ {o.price:.2f} · {o.duration_minutes} min"}
        for o in options
    ]
    ctx["last_list"] = [
        {"row_id": o.row_key, "payload": str(o.id), "service_name": o.name}
        for o in options
    ]
    session.context = ctx
    session.state   = STATE_ESCOLHENDO_SERVICO

    nome = first_name(ctx.get("customer_name", ""))
    sender.send_list(instance, whatsapp_id, "✂️ Nossos serviços",
                     messages.escolha_servico(nome), rows)


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_profissional,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    selected = next(
        (e for e in ctx.get("last_list", []) if e.get("payload") == payload),
        {},
    )
    if not selected:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["service_id"]   = payload
    ctx["service_name"] = selected.get("service_name", "")
    session.context     = ctx
    start_escolhendo_profissional(db, session, company_id, instance, whatsapp_id)