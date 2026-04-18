"""Handlers do estado ESCOLHENDO_DATA."""
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import label_date, first_name

STATE_ESCOLHENDO_DATA = "ESCOLHENDO_DATA"


def send_escolher_data(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs
) -> None:
    """
    Exibe a lista de datas disponíveis para seleção.
    Assinatura padronizada com (db, session, company_id, instance, whatsapp_id)
    para consistência com os outros start/send handlers.
    """
    ctx   = dict(session.context or {})
    today = datetime.now(timezone.utc).date()

    rows, last_list = [], []
    for i in range(7):
        d          = today + timedelta(days=i)
        row_id     = d.isoformat()
        date_label = label_date(d)
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
    start_escolhendo_horario,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["selected_date"] = payload
    session.context      = ctx
    start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
