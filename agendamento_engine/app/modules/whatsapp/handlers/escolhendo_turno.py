"""Handler do estado ESCOLHENDO_TURNO — seleção de período do dia."""
import logging
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.booking.engine import booking_engine

logger = logging.getLogger(__name__)

STATE_ESCOLHENDO_TURNO = "ESCOLHENDO_TURNO"

# Ordem e definição dos turnos
_TURNOS = [
    {"payload": "manha", "label": "Manhã", "row_id": "turno_manha"},
    {"payload": "tarde", "label": "Tarde", "row_id": "turno_tarde"},
    {"payload": "noite", "label": "Noite", "row_id": "turno_noite"},
]


def _get_shift_counts(db: Session, ctx: dict, company_id: UUID) -> dict[str, int]:
    """
    Retorna um dict {shift: slot_count} para a data selecionada.
    Retorna contagens zeradas se não for possível calcular.
    """
    date_str = ctx.get("selected_date")
    svc_id_raw = ctx.get("service_id")

    if not date_str or not svc_id_raw:
        return {t["payload"]: 0 for t in _TURNOS}

    try:
        target_date = datetime.fromisoformat(date_str).date()
        svc_id = UUID(svc_id_raw)
        prof_id_raw = ctx.get("professional_id")
        prof_id = UUID(prof_id_raw) if prof_id_raw else None
        tz = ctx.get("company_timezone") or "America/Sao_Paulo"

        shift_options = booking_engine.get_shift_availability(
            db, company_id, prof_id, svc_id, target_date, company_timezone=tz,
        )
        return {o.shift: o.slot_count for o in shift_options}

    except Exception:
        logger.warning("Falha ao calcular disponibilidade por turno", exc_info=True)
        return {t["payload"]: 0 for t in _TURNOS}


def send_escolher_turno(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs,
) -> None:
    """
    Exibe as opções de turno com contagem de horários disponíveis.
    Turnos sem disponibilidade são exibidos com sufixo '— indisponível'.
    Chamado após o usuário escolher a data.
    """
    ctx = dict(session.context or {})

    # Calcular disponibilidade por turno
    counts = _get_shift_counts(db, ctx, company_id)

    # Persistir disponibilidade no contexto para uso no handle()
    ctx["turno_availability"] = counts

    last_list = []
    buttons = []

    for t in _TURNOS:
        shift = t["payload"]
        count = counts.get(shift, 0)
        has_slots = count > 0

        if has_slots:
            label = f"{t['label']} ({count} horário{'s' if count > 1 else ''})"
        else:
            label = f"{t['label']} — indisponível"

        last_list.append({
            "row_id":  t["row_id"],
            "payload": shift,
            "title":   label,
        })
        buttons.append({
            "buttonId":   t["row_id"],
            "buttonText": {"displayText": label},
        })

    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_ESCOLHENDO_TURNO

    sender.send_buttons(
        instance, whatsapp_id,
        "Qual período prefere?",
        buttons,
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_escolhendo_horario,
    send_escolher_turno_fn=None,
) -> None:
    ctx = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload not in ("manha", "tarde", "noite"):
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    # Verificar se o turno tem horários disponíveis
    availability = ctx.get("turno_availability", {})
    count = availability.get(payload, -1)   # -1 = não calculado (pass-through)

    if count == 0:
        # Turno sem horários — reexibir lista com feedback
        turno_labels = {"manha": "manhã", "tarde": "tarde", "noite": "noite"}
        turno_label = turno_labels.get(payload, payload)
        sender.send_text(
            instance, whatsapp_id,
            f"😕 Não há horários disponíveis de *{turno_label}* nessa data.\n\n"
            "Escolha outro turno ou clique em *0* para voltar ao menu.",
        )
        # Re-exibir opções de turno sem avançar o estado
        fn = send_escolher_turno_fn or send_escolher_turno
        fn(db, session, company_id, instance, whatsapp_id)
        return

    ctx["selected_turno"] = payload
    ctx.pop("slot_offset", None)   # nova seleção de turno = página 0 de horários
    session.context = ctx
    start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
