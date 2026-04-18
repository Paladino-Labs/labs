"""Handler do estado MENU_PRINCIPAL."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import resolve_input as _resolve_input
from app.modules.whatsapp.handlers.inicio import show_menu_principal

STATE_ESCOLHENDO_SERVICO  = "ESCOLHENDO_SERVICO"
STATE_VER_AGENDAMENTOS    = "VER_AGENDAMENTOS"
STATE_HUMANO              = "HUMANO"


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    start_escolhendo_servico,
    handle_ver_agendamentos,
) -> None:
    ctx = dict(session.context or {})

    # resolve_input aceita tanto o row_id exato ("opt_agendar") quanto
    # número digitado ("1", "2", "3") do fallback de texto.
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if payload == "opt_agendar":
        session.state   = STATE_ESCOLHENDO_SERVICO
        session.context = ctx
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "opt_ver_agendamentos":
        session.state   = STATE_VER_AGENDAMENTOS
        session.context = ctx
        handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return

    if payload == "opt_humano":
        session.state   = STATE_HUMANO
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.HUMANO_CHAMADO)
        return

    # Nenhuma opção reconhecida — reapresenta o menu
    show_menu_principal(session, ctx, instance, whatsapp_id,
                        ctx.get("company_name", ""), ctx.get("customer_name"))