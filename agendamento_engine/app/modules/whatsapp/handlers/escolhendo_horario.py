"""Handlers do estado ESCOLHENDO_HORARIO."""
import uuid as uuidlib
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import label_date
from app.modules.booking.engine import booking_engine
from app.core.config import settings


def _get_tz(ctx: dict) -> ZoneInfo:
    tz_name = ctx.get("company_timezone") or "America/Sao_Paulo"
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/Sao_Paulo")

STATE_ESCOLHENDO_HORARIO = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA    = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO        = "CONFIRMANDO"

# Busca até N×limit slots para ter folga de paginação
_POOL_MULTIPLIER = 5


def _filter_by_turno(slots, turno: str | None, tz: ZoneInfo | None = None):
    """Filtra slots pelo turno selecionado usando hora local da empresa. Sem turno → retorna todos."""
    if not turno:
        return slots
    if tz is None:
        tz = ZoneInfo("America/Sao_Paulo")

    def local_hour(s) -> int:
        return s.start_at.astimezone(tz).hour

    if turno == "manha":
        return [s for s in slots if local_hour(s) < 12]
    if turno == "tarde":
        return [s for s in slots if 12 <= local_hour(s) < 18]
    if turno == "noite":
        return [s for s in slots if local_hour(s) >= 18]
    return slots


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
    turno    = ctx.get("selected_turno")       # "manha" | "tarde" | "noite" | None
    prof_id_val = UUID(prof_raw) if prof_raw else None

    n      = settings.BOT_MAX_SLOTS_DISPLAYED
    pool   = n * _POOL_MULTIPLIER
    offset = int(ctx.get("slot_offset", 0))

    # ── Busca pool de slots ───────────────────────────────────────────────────
    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
        raw_slots = booking_engine.list_available_slots(
            db, company_id, prof_id_val, svc_id, target_date, limit=pool,
        )
    else:
        raw_slots = booking_engine.list_next_available_slots(
            db, company_id, prof_id_val, svc_id, days=7, limit=pool,
        )

    # ── Filtra pelo turno escolhido (horário local da empresa) ───────────────
    tz        = _get_tz(ctx)
    all_slots = _filter_by_turno(raw_slots, turno, tz)
    any_prof  = (prof_raw is None)

    # ── Sem horários no turno ─────────────────────────────────────────────────
    if not all_slots:
        turno_label = {"manha": "manhã", "tarde": "tarde", "noite": "noite"}.get(turno, "")
        msg = (
            messages.SEM_HORARIOS
            if not turno_label
            else f"😕 Não há horários disponíveis {f'de {turno_label} ' if turno_label else ''}nessa data."
                 "\n\nDigite *0* para voltar ao menu ou escolha outra data abaixo."
        )
        ctx["last_list"] = [
            {"row_id": "opt_outra_data", "payload": "outra_data",
             "title": "📅 Escolher outra data"},
        ]
        session.context = ctx
        session.state   = STATE_ESCOLHENDO_HORARIO
        sender.send_buttons(
            instance, whatsapp_id, msg,
            [{"buttonId": "opt_outra_data",
              "buttonText": {"displayText": "📅 Escolher outra data"}}],
        )
        return

    # ── Paginação ─────────────────────────────────────────────────────────────
    display_slots = all_slots[offset:offset + n]
    if not display_slots:
        # offset obsoleto (slots mudaram) — volta ao início
        offset = 0
        ctx["slot_offset"] = 0
        display_slots = all_slots[:n]

    has_more     = len(all_slots) > (offset + n)
    has_previous = offset > 0

    # ── Monta rows / last_list ────────────────────────────────────────────────
    rows, last_list = [], []
    for s in display_slots:
        row_id       = f"{s.start_at.isoformat()}|{s.professional_id}"
        local_start  = s.start_at.astimezone(tz)
        time_label   = local_start.strftime("%H:%M")
        date_label   = label_date(local_start.date())

        # Formato: "Hoje (16/04) — 12:15" ou "Hoje (16/04) — 12:15 — Hemerson"
        # description sempre vazio — evita que o fallback texto duplique o nome
        if any_prof:
            title_str = f"{date_label} — {time_label} — {s.professional_name}"
        else:
            title_str = f"{date_label} — {time_label}"

        rows.append({
            "rowId":       row_id,
            "title":       title_str,
            "description": "",          # sempre vazio: impede "nome — nome" no fallback
        })
        last_list.append({"row_id": row_id, "payload": row_id,
                          "professional_name": s.professional_name,
                          "title": title_str})

    if has_previous:
        rows.append({"rowId": "opt_menos_horarios", "title": "Mais cedo", "description": ""})
        last_list.append({"row_id": "opt_menos_horarios", "payload": "menos_horarios",
                          "title": "Mais cedo"})

    if has_more:
        rows.append({"rowId": "opt_mais_horarios", "title": "Mais tarde", "description": ""})
        last_list.append({"row_id": "opt_mais_horarios", "payload": "mais_horarios",
                          "title": "Mais tarde"})

    rows.append({"rowId": "opt_outra_data", "title": "📅 Escolher outra data", "description": ""})
    last_list.append({"row_id": "opt_outra_data", "payload": "outra_data",
                      "title": "📅 Escolher outra data"})

    ctx["last_list"]   = last_list
    ctx["slot_offset"] = offset
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
        ctx.pop("selected_turno", None)
        session.context = ctx
        send_escolher_data(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "menos_horarios":
        n = settings.BOT_MAX_SLOTS_DISPLAYED
        ctx["slot_offset"] = max(0, int(ctx.get("slot_offset", 0)) - n)
        session.context = ctx
        start(db, session, company_id, instance, whatsapp_id,
              send_escolher_data=send_escolher_data,
              send_confirmacao_resumo=send_confirmacao_resumo)
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
    ctx.pop("slot_offset", None)

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
