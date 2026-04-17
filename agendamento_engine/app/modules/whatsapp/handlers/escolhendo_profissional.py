"""Handlers do estado ESCOLHENDO_PROFISSIONAL."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.professionals import service as professional_svc

STATE_ESCOLHENDO_PROFISSIONAL = "ESCOLHENDO_PROFISSIONAL"


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    send_escolher_data,
) -> None:
    ctx        = dict(session.context or {})
    service_id = UUID(ctx["service_id"])
    profs      = professional_svc.list_by_service(db, company_id, service_id)

    if not profs:
        sender.send_text(
            instance, whatsapp_id,
            "😕 Não há profissionais disponíveis para esse serviço no momento.",
        )
        return

    rows = [{"rowId": str(p.id), "title": p.name, "description": ""} for p in profs]
    rows.append({"rowId": "prof_any", "title": "👥 Qualquer disponível", "description": ""})

    ctx["last_list"] = (
        [{"row_id": str(p.id), "payload": str(p.id)} for p in profs]
        + [{"row_id": "prof_any", "payload": "any"}]
    )
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

    if payload == "any":
        ctx["professional_id"]   = None
        ctx["professional_name"] = "Qualquer disponível"
    else:
        try:
            prof = professional_svc.get_professional_or_404(db, company_id, UUID(payload))
            ctx["professional_id"]   = payload
            ctx["professional_name"] = prof.name
        except Exception:
            sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
            return

    session.context = ctx
    send_escolher_data(db, session, company_id, instance, whatsapp_id)