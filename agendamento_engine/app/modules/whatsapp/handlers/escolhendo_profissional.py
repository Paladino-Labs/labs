"""Handlers do estado ESCOLHENDO_PROFISSIONAL."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.booking.engine import booking_engine

STATE_ESCOLHENDO_PROFISSIONAL = "ESCOLHENDO_PROFISSIONAL"


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    send_escolher_data,
) -> None:
    ctx        = dict(session.context or {})
    service_id = UUID(ctx["service_id"])
    options    = booking_engine.list_professionals(db, company_id, service_id)

    # Filtra a opção "Qualquer disponível" para verificar se há profissionais reais
    real_profs = [o for o in options if o.id is not None]
    if not real_profs:
        sender.send_text(
            instance, whatsapp_id,
            "😕 Não há profissionais disponíveis para esse serviço no momento.",
        )
        return

    rows = [{"rowId": o.row_key, "title": o.name, "description": ""} for o in options]

    ctx["last_list"] = [
        {"row_id": o.row_key,
         "payload": str(o.id) if o.id else "any",
         "professional_name": o.name,
         "title": o.name}
        for o in options
    ]
    session.context = ctx
    session.state   = STATE_ESCOLHENDO_PROFISSIONAL

    svc = ctx.get("service_name", "")
    sender.send_list(instance, whatsapp_id, "👤 Escolha o profissional",
                     messages.escolha_profissional(svc), rows)


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    send_escolher_data,
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

    if payload == "any":
        ctx["professional_id"]   = None
        ctx["professional_name"] = selected.get("professional_name", "Qualquer disponível")
    else:
        ctx["professional_id"]   = payload
        ctx["professional_name"] = selected.get("professional_name", "")

    session.context = ctx
    send_escolher_data(db, session, company_id, instance, whatsapp_id)