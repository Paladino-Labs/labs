"""Handlers do estado ESCOLHENDO_DATA."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.booking.engine import booking_engine

STATE_ESCOLHENDO_DATA = "ESCOLHENDO_DATA"

_DAYS_AHEAD = 14  # janela de busca de datas disponíveis


def send_escolher_data(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs
) -> None:
    """
    Exibe a lista de datas disponíveis para seleção.

    Usa booking_engine.list_available_dates() para filtrar apenas dias
    com disponibilidade real — evita o usuário escolher uma data vazia.

    Assinatura padronizada com (db, session, company_id, instance, whatsapp_id)
    para consistência com os outros start/send handlers.
    """
    ctx = dict(session.context or {})

    svc_id_raw  = ctx.get("service_id")
    prof_id_raw = ctx.get("professional_id")  # pode ser None ou UUID string

    if not svc_id_raw:
        # Contexto inválido — volta ao menu
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    svc_id  = UUID(svc_id_raw)
    prof_id = UUID(prof_id_raw) if prof_id_raw else None

    date_options = booking_engine.list_available_dates(
        db, company_id, prof_id, svc_id, days=_DAYS_AHEAD
    )

    # Filtra apenas dias com disponibilidade real
    available = [d for d in date_options if d.has_availability]

    if not available:
        svc  = ctx.get("service_name", "serviço")
        prof = ctx.get("professional_name", "")
        msg  = (
            f"😕 Não há horários disponíveis para *{svc}*"
            + (f" com *{prof}*" if prof and prof != "Qualquer disponível" else "")
            + f" nos próximos {_DAYS_AHEAD} dias.\n\n"
            "Digite *0* para voltar ao menu principal."
        )
        sender.send_text(instance, whatsapp_id, msg)
        return

    rows      = []
    last_list = []
    for d in available:
        row_id     = d.date.isoformat()   # payload: "2026-04-20"
        date_label = d.label              # "Hoje (20/04)", "Amanhã (21/04)", etc.
        rows.append({"rowId": row_id, "title": date_label, "description": ""})
        last_list.append({"row_id": row_id, "payload": row_id, "title": date_label})

    ctx["last_list"] = last_list
    session.context  = ctx
    session.state    = STATE_ESCOLHENDO_DATA

    nome = first_name(ctx.get("customer_name", ""))
    svc  = ctx.get("service_name", "")
    prof = ctx.get("professional_name", "")

    sender.send_list(
        instance, whatsapp_id,
        messages.escolha_data_titulo(svc),
        messages.escolha_data_descricao(nome, prof),
        rows,
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_turno,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["selected_date"] = payload
    ctx.pop("slot_offset", None)    # nova data = página 0 de horários
    ctx.pop("selected_turno", None) # nova data = escolher turno novamente
    session.context      = ctx
    start_escolhendo_turno(db, session, company_id, instance, whatsapp_id)
