"""Handlers do estado GERENCIANDO_AGENDAMENTO."""
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.session import reset_session
from app.modules.appointments import service as appointment_svc
from app.core.config import settings

logger = logging.getLogger(__name__)

STATE_GERENCIANDO_AGENDAMENTO = "GERENCIANDO_AGENDAMENTO"
STATE_CANCELANDO              = "CANCELANDO"
STATE_REAGENDANDO             = "REAGENDANDO"


def start(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, appt,
) -> None:
    ctx = session.context or {}
    session.state = STATE_GERENCIANDO_AGENDAMENTO

    svc_name   = appt.services[0].service_name if appt.services else "Serviço"
    prof_name  = appt.professional.name if appt.professional else "?"
    slot_label = appt.start_at.strftime("%d/%m às %H:%M")
    remaining  = appt.start_at - datetime.now(timezone.utc)
    can_change = remaining > timedelta(hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE)

    text      = messages.gerenciar_agendamento(svc_name, prof_name, slot_label)
    buttons   = []
    last_list = []

    if can_change:
        buttons.append({"buttonId": "opt_reagendar",
                        "buttonText": {"displayText": "🔄 Reagendar"}})
        last_list.append({"row_id": "opt_reagendar", "payload": "opt_reagendar",
                          "title": "🔄 Reagendar"})

    buttons.append(
        {"buttonId": "opt_cancelar_appt",
         "buttonText": {"displayText": "❌ Cancelar agendamento"}},
    )
    last_list.append(
        {"row_id": "opt_cancelar_appt", "payload": "opt_cancelar_appt",
         "title": "❌ Cancelar agendamento"},
    )

    ctx = dict(ctx)
    ctx["last_list"] = last_list
    session.context  = ctx
    sender.send_buttons(instance, whatsapp_id, text, buttons)


def _show_reagendamento_submenu(instance: str, whatsapp_id: str, ctx: dict,
                                session: BotSession) -> None:
    """Exibe o sub-menu: mesmo serviço/profissional ou mudar serviço."""
    ctx = dict(ctx)
    ctx["last_list"] = [
        {"row_id": "opt_reagendar_mesmo",  "payload": "reagendar_mesmo",
         "title": "🕐 Mesmo serviço e profissional"},
        {"row_id": "opt_reagendar_mudar",  "payload": "reagendar_mudar",
         "title": "🔁 Mudar serviço"},
    ]
    session.context = ctx
    sender.send_buttons(
        instance, whatsapp_id,
        "Como deseja reagendar?",
        [
            {"buttonId": "opt_reagendar_mesmo",
             "buttonText": {"displayText": "🕐 Mesmo serviço e profissional"}},
            {"buttonId": "opt_reagendar_mudar",
             "buttonText": {"displayText": "🔁 Mudar serviço"}},
        ],
    )


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    handle_ver_agendamentos,
    start_cancelando,
    start_escolhendo_horario,
    start_escolhendo_servico=None,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "opt_cancelar_appt":
        session.state = STATE_CANCELANDO
        start_cancelando(db, session, company_id, whatsapp_id, instance)
        return

    # ── Reagendar: primeiro clique → mostra sub-menu ──────────────────────────
    if payload == "opt_reagendar":
        appt_id = UUID(ctx["managing_appointment_id"])
        try:
            appt = appointment_svc.get_appointment_or_404(db, company_id, appt_id)
        except Exception:
            reset_session(session)
            return

        remaining = appt.start_at - datetime.now(timezone.utc)
        if remaining <= timedelta(hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE):
            sender.send_text(
                instance, whatsapp_id,
                messages.reagendamento_fora_prazo(settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE),
            )
            return

        # Salva dados do agendamento original para poder bifurcar em confirmando.py
        ctx = dict(ctx)
        original_svc_id = (str(appt.services[0].service_id)
                           if appt.services else ctx.get("service_id", ""))
        ctx["original_service_id"]    = original_svc_id
        ctx["original_professional_id"] = str(appt.professional_id)
        ctx["is_rescheduling"]        = True
        session.context = ctx

        _show_reagendamento_submenu(instance, whatsapp_id, ctx, session)
        return

    # ── Sub-opção: mesmo serviço e profissional ───────────────────────────────
    if payload == "reagendar_mesmo":
        appt_id = UUID(ctx["managing_appointment_id"])
        try:
            appt = appointment_svc.get_appointment_or_404(db, company_id, appt_id)
        except Exception:
            reset_session(session)
            return

        ctx = dict(ctx)
        if appt.services:
            ctx["service_id"]   = str(appt.services[0].service_id)
            ctx["service_name"] = appt.services[0].service_name
        ctx["professional_id"]   = str(appt.professional_id)
        ctx["professional_name"] = appt.professional.name if appt.professional else ""
        ctx.pop("selected_date", None)
        ctx.pop("slot_start_at", None)
        ctx.pop("slot_offset", None)
        session.context = ctx
        session.state   = STATE_REAGENDANDO
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    # ── Sub-opção: mudar serviço (recomeça seleção do zero) ───────────────────
    if payload == "reagendar_mudar":
        if not start_escolhendo_servico:
            # Fallback: comportamento de "mesmo serviço" se função não injetada
            sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
            return

        ctx = dict(ctx)
        # Limpa contexto de serviço/profissional/slot para recomeçar do início
        for key in ("service_id", "service_name", "professional_id", "professional_name",
                    "selected_date", "slot_start_at", "slot_offset"):
            ctx.pop(key, None)
        session.context = ctx
        session.state   = STATE_REAGENDANDO
        start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
