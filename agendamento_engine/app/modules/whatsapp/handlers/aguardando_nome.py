"""Handlers dos estados AGUARDANDO_NOME e CONFIRMAR_NOME."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.customers import service as customer_svc

STATE_AGUARDANDO_NOME = "AGUARDANDO_NOME"
STATE_CONFIRMAR_NOME  = "CONFIRMAR_NOME"
STATE_MENU_PRINCIPAL  = "MENU_PRINCIPAL"


def handle_aguardando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    nome = user_input.strip()
    if len(nome) < 2:
        sender.send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    ctx = dict(session.context or {})
    ctx["nome_temp"] = nome
    session.context = ctx
    session.state = STATE_CONFIRMAR_NOME
    sender.send_text(instance, whatsapp_id, messages.confirmar_nome(nome))


def handle_confirmando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    start_escolhendo_servico,
) -> None:
    resposta  = user_input.strip().lower()
    ctx       = dict(session.context or {})
    nome_temp = ctx.get("nome_temp")

    if not nome_temp:
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    if resposta in ("1", "sim", "s", "ok", "isso", "confirmar"):
        customer = customer_svc.get_or_create_by_phone(db, company_id, whatsapp_id, nome_temp)
        ctx["customer_id"]   = str(customer.id)
        ctx["customer_name"] = customer.name
        ctx.pop("nome_temp", None)
        session.context = ctx
        session.state = STATE_MENU_PRINCIPAL

        nome_curto = first_name(customer.name)
        sender.send_text(instance, whatsapp_id, messages.boas_vindas_nome_confirmado(nome_curto))
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    if resposta in ("2", "não", "nao", "n", "errado", "corrigir"):
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)