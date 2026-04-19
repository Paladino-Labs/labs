"""Handler do estado ESCOLHENDO_TURNO — seleção de período do dia."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender

STATE_ESCOLHENDO_TURNO = "ESCOLHENDO_TURNO"

# Turnos disponíveis e seus rótulos
_TURNOS = [
    {"payload": "manha", "label": "🌅 Manhã (até 12h)",    "title": "🌅 Manhã (até 12h)"},
    {"payload": "tarde", "label": "🌤 Tarde (12h – 18h)",  "title": "🌤 Tarde (12h – 18h)"},
    {"payload": "noite", "label": "🌙 Noite (após 18h)",   "title": "🌙 Noite (após 18h)"},
]


def send_escolher_turno(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs,
) -> None:
    """
    Exibe as opções de turno (manhã / tarde / noite).
    Chamado após o usuário escolher a data.
    """
    ctx = dict(session.context or {})

    ctx["last_list"] = [
        {"row_id": f"turno_{t['payload']}", "payload": t["payload"], "title": t["title"]}
        for t in _TURNOS
    ]
    session.context = ctx
    session.state   = STATE_ESCOLHENDO_TURNO

    sender.send_buttons(
        instance, whatsapp_id,
        "Qual período prefere?",
        [
            {"buttonId": f"turno_{t['payload']}",
             "buttonText": {"displayText": t["label"]}}
            for t in _TURNOS
        ],
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_horario,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload not in ("manha", "tarde", "noite"):
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["selected_turno"] = payload
    ctx.pop("slot_offset", None)   # nova seleção de turno = página 0 de horários
    session.context = ctx
    start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
