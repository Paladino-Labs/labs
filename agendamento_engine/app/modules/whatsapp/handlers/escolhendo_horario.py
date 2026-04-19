"""Handlers do estado ESCOLHENDO_HORARIO."""
import uuid as uuidlib
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.booking.engine import booking_engine
from app.modules.booking.schemas import SlotOption
from app.core.config import settings

STATE_ESCOLHENDO_HORARIO = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA    = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO        = "CONFIRMANDO"

# Busca até 5x o limite para ter material para distribuição e paginação
_POOL_MULTIPLIER = 5


def _distribute_slots(slots: list[SlotOption], limit: int) -> list[SlotOption]:
    """
    Seleciona `limit` slots distribuídos por faixa horária e os devolve
    em ordem cronológica.

    Faixas:
      manhã → hora < 12
      tarde  → 12 ≤ hora < 18
      noite  → hora ≥ 18

    Se alguma faixa estiver vazia, os vagas não preenchidas são completadas
    com o restante disponível em ordem cronológica.
    """
    manha = [s for s in slots if s.start_at.hour < 12]
    tarde = [s for s in slots if 12 <= s.start_at.hour < 18]
    noite = [s for s in slots if s.start_at.hour >= 18]

    base   = limit // 3
    extras = limit % 3  # distribui extras: 1º manhã, 2º tarde

    selected = (
        manha[:base + (1 if extras > 0 else 0)] +
        tarde[:base + (1 if extras > 1 else 0)] +
        noite[:base]
    )

    # Completa se alguma faixa estava vazia
    if len(selected) < limit:
        used = {(s.start_at, s.professional_id) for s in selected}
        filler = [s for s in slots if (s.start_at, s.professional_id) not in used]
        selected += filler[:limit - len(selected)]

    selected.sort(key=lambda s: s.start_at)
    return selected[:limit]


def start(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    send_escolher_data,
    send_confirmacao_resumo,
) -> None:
    ctx      = dict(session.context or {})
    svc_id   = UUID(ctx["service_id"])
    prof_raw = ctx.get("professional_id")
    date_str = ctx.get("selected_date")
    prof_id_val = UUID(prof_raw) if prof_raw else None

    n      = settings.BOT_MAX_SLOTS_DISPLAYED
    pool   = n * _POOL_MULTIPLIER
    offset = int(ctx.get("slot_offset", 0))

    # ── Busca pool de slots ───────────────────────────────────────────────────
    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
        all_slots = booking_engine.list_available_slots(
            db, company_id, prof_id_val, svc_id, target_date, limit=pool,
        )
    else:
        all_slots = booking_engine.list_next_available_slots(
            db, company_id, prof_id_val, svc_id, days=7, limit=pool,
        )

    any_prof = (prof_raw is None)

    # ── Sem horários ──────────────────────────────────────────────────────────
    if not all_slots:
        ctx["last_list"] = [
            {"row_id": "opt_outra_data", "payload": "outra_data",
             "title": "📅 Escolher outra data"},
        ]
        session.context = ctx
        session.state   = STATE_ESCOLHENDO_HORARIO
        sender.send_buttons(
            instance, whatsapp_id, messages.SEM_HORARIOS,
            [
                {"buttonId": "opt_outra_data",
                 "buttonText": {"displayText": "📅 Escolher outra data"}},
            ],
        )
        return

    # ── Seleciona página de slots ─────────────────────────────────────────────
    if offset == 0:
        # Primeira página: distribui pelos períodos do dia
        display_slots = _distribute_slots(all_slots, n)
    else:
        # Páginas seguintes: ordem cronológica a partir do offset
        display_slots = all_slots[offset:offset + n]
        if not display_slots:
            # offset expirado (slots mudaram) — volta ao início
            ctx["slot_offset"] = 0
            display_slots = _distribute_slots(all_slots, n)
            offset = 0

    has_more = len(all_slots) > (offset + n)

    # ── Monta rows / last_list ────────────────────────────────────────────────
    rows, last_list = [], []
    for s in display_slots:
        row_id     = f"{s.start_at.isoformat()}|{s.professional_id}"
        time_label = s.start_at.strftime("%H:%M")
        title_str  = f"{time_label} — {s.professional_name}" if any_prof else time_label
        rows.append({
            "rowId":       row_id,
            "title":       title_str,
            "description": s.professional_name if any_prof else "",
        })
        last_list.append({"row_id": row_id, "payload": row_id,
                          "professional_name": s.professional_name,
                          "title": title_str})

    # "Mais horários" — só se houver próxima página
    if has_more:
        rows.append({
            "rowId": "opt_mais_horarios",
            "title": "📋 Ver mais horários",
            "description": "",
        })
        last_list.append({"row_id": "opt_mais_horarios", "payload": "mais_horarios",
                          "title": "📋 Ver mais horários"})

    rows.append({"rowId": "opt_outra_data", "title": "📅 Escolher outra data", "description": ""})
    last_list.append({"row_id": "opt_outra_data", "payload": "outra_data",
                      "title": "📅 Escolher outra data"})

    ctx["last_list"]   = last_list
    ctx["slot_offset"] = offset   # mantém o offset atual (incrementado só em mais_horarios)
    session.context    = ctx
    session.state      = STATE_ESCOLHENDO_HORARIO

    prof_label = ctx.get("professional_name", "")
    sender.send_list(
        instance, whatsapp_id,
        "🕐 Horários disponíveis",
        messages.escolha_horario(ctx["service_name"], prof_label),
        rows,
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    send_escolher_data,
    send_confirmacao_resumo,
) -> None:
    ctx     = dict(session.context or {})
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    if payload == "outra_data":
        ctx.pop("slot_offset", None)
        session.context = ctx
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "mais_horarios":
        n = settings.BOT_MAX_SLOTS_DISPLAYED
        ctx["slot_offset"] = int(ctx.get("slot_offset", 0)) + n
        session.context = ctx
        start(db, session, company_id, instance, whatsapp_id,
              send_escolher_data=send_escolher_data,
              send_confirmacao_resumo=send_confirmacao_resumo)
        return

    if "|" not in payload:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    try:
        start_str, prof_id_str = payload.split("|", 1)
    except ValueError:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["slot_start_at"] = start_str
    ctx.pop("slot_offset", None)   # reseta paginação ao confirmar slot

    if not ctx.get("professional_id"):
        ctx["professional_id"] = prof_id_str
        selected = next(
            (e for e in ctx.get("last_list", []) if e.get("payload") == payload),
            {},
        )
        if selected.get("professional_name"):
            ctx["professional_name"] = selected["professional_name"]

    ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
    session.context = ctx
    session.state   = STATE_CONFIRMANDO
    send_confirmacao_resumo(instance, whatsapp_id, ctx)
