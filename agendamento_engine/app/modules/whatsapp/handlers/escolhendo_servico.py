"""Handlers do estado ESCOLHENDO_SERVICO."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.services import service as service_svc

STATE_ESCOLHENDO_SERVICO = "ESCOLHENDO_SERVICO"


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    services = service_svc.list_services(db, company_id, active_only=True)
    ctx      = dict(session.context or {})

    if not services:
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
        {"rowId": str(s.id), "title": s.name,
         "description": f"R$ {s.price:.2f} · {s.duration} min"}
        for s in services
    ]
    ctx["last_list"] = [
        {"row_id": str(s.id), "payload": str(s.id)}
        for s in services
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

    try:
        service = service_svc.get_service_or_404(db, company_id, UUID(payload))
    except Exception:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["service_id"]   = payload
    ctx["service_name"] = service.name
    session.context     = ctx
    start_escolhendo_profissional(db, session, company_id, instance, whatsapp_id)