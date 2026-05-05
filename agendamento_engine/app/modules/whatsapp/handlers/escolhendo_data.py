"""Handlers do estado ESCOLHENDO_DATA."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.booking.engine import booking_engine
from app.core.config import settings

STATE_ESCOLHENDO_DATA = "ESCOLHENDO_DATA"

# payloads reservados para navegação de página
_PAYLOAD_NEXT = "__dates_next__"
_PAYLOAD_PREV = "__dates_prev__"


def send_escolher_data(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs
) -> None:
    """
    Exibe a lista paginada de datas disponíveis para seleção (janela de 7 dias).

    Lê `date_offset_days` do contexto da sessão — preserva a página atual
    quando o usuário navega entre janelas.

    Assinatura padronizada com (db, session, company_id, instance, whatsapp_id)
    para consistência com os outros start/send handlers.
    """
    ctx = dict(session.context or {})

    svc_id_raw  = ctx.get("service_id")
    prof_id_raw = ctx.get("professional_id")

    if not svc_id_raw:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    svc_id      = UUID(svc_id_raw)
    prof_id     = UUID(prof_id_raw) if prof_id_raw else None
    offset_days = max(0, int(ctx.get("date_offset_days", 0)))

    dates, has_next, has_previous = booking_engine.list_available_dates_paged(
        db, company_id, prof_id, svc_id,
        offset_days=offset_days,
        window=settings.DATE_WINDOW_SIZE,
    )

    # Filtra apenas dias com disponibilidade real
    available = [d for d in dates if d.has_availability]

    if not available and not has_next and not has_previous:
        # Sem disponibilidade em nenhuma direção
        svc  = ctx.get("service_name", "serviço")
        prof = ctx.get("professional_name", "")
        msg  = (
            f"😕 Não há horários disponíveis para *{svc}*"
            + (f" com *{prof}*" if prof and prof != "Qualquer disponível" else "")
            + f" nos próximos {settings.DATE_WINDOW_SIZE} dias.\n\n"
            "Digite *0* para voltar ao menu principal."
        )
        sender.send_text(instance, whatsapp_id, msg)
        return

    rows      = []
    last_list = []

    if not available:
        # Janela atual sem disponibilidade — indica ao usuário que pode navegar
        rows.append({"rowId": "__empty__", "title": "Nenhum dia disponível nesta semana", "description": ""})
        last_list.append({"row_id": "__empty__", "payload": "__empty__", "title": ""})
    else:
        for d in available:
            row_id     = d.date.isoformat()
            date_label = d.label
            rows.append({"rowId": row_id, "title": date_label, "description": ""})
            last_list.append({"row_id": row_id, "payload": row_id, "title": date_label})

    # Botões de navegação no final da lista
    if has_previous:
        rows.append({"rowId": _PAYLOAD_PREV, "title": "⬅️ 7 dias anteriores", "description": ""})
        last_list.append({"row_id": _PAYLOAD_PREV, "payload": _PAYLOAD_PREV, "title": "⬅️ 7 dias anteriores"})

    if has_next:
        rows.append({"rowId": _PAYLOAD_NEXT, "title": "➡️ Próximos 7 dias", "description": ""})
        last_list.append({"row_id": _PAYLOAD_NEXT, "payload": _PAYLOAD_NEXT, "title": "➡️ Próximos 7 dias"})

    # Persistir offset e lista no contexto
    ctx["date_offset_days"] = offset_days
    ctx["dates_has_next"]   = has_next
    ctx["dates_has_previous"] = has_previous
    ctx["last_list"]        = last_list
    session.context         = ctx
    session.state           = STATE_ESCOLHENDO_DATA

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

    # Navegação de página — não seleciona data
    if payload == _PAYLOAD_NEXT:
        max_offset = max(0, settings.DATE_MAX_ADVANCE_DAYS - settings.DATE_WINDOW_SIZE)
        offset = min(int(ctx.get("date_offset_days", 0)) + settings.DATE_WINDOW_SIZE, max_offset)
        ctx["date_offset_days"] = offset
        session.context = ctx
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if payload == _PAYLOAD_PREV:
        offset = max(0, int(ctx.get("date_offset_days", 0)) - settings.DATE_WINDOW_SIZE)
        ctx["date_offset_days"] = offset
        session.context = ctx
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "__empty__":
        # Usuário clicou em "nenhum dia disponível" — reexibe a lista com navegação
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    # Data selecionada — limpar offset de navegação e estado de turno anterior
    ctx["selected_date"] = payload
    ctx.pop("date_offset_days", None)
    ctx.pop("dates_has_next", None)
    ctx.pop("dates_has_previous", None)
    ctx.pop("slot_offset", None)
    ctx.pop("selected_turno", None)
    ctx.pop("turno_availability", None)
    session.context      = ctx
    start_escolhendo_turno(db, session, company_id, instance, whatsapp_id)
