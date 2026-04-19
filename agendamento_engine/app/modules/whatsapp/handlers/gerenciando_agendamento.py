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

    buttons += [
        {"buttonId": "opt_cancelar_appt",
         "buttonText": {"displayText": "❌ Cancelar agendamento"}},
        {"buttonId": "opt_voltar",
         "buttonText": {"displayText": "← Voltar"}},
    ]
    last_list += [
        {"row_id": "opt_cancelar_appt", "payload": "opt_cancelar_appt",
         "title": "❌ Cancelar agendamento"},
        {"row_id": "opt_voltar",        "payload": "voltar",
         "title": "← Voltar"},
    ]

    ctx = dict(ctx)
    ctx["last_list"] = last_list
    session.context  = ctx
    sender.send_buttons(instance, whatsapp_id, text, buttons)


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    handle_ver_agendamentos,
    start_cancelando,
    start_escolhendo_horario,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "voltar":
        handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return

    if payload == "opt_cancelar_appt":
        session.state = STATE_CANCELANDO
        start_cancelando(db, session, company_id, whatsapp_id, instance)
        return

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

        ctx = dict(ctx)
        if appt.services:
            ctx["service_id"]   = str(appt.services[0].service_id)
            ctx["service_name"] = appt.services[0].service_name
        ctx["professional_id"]   = str(appt.professional_id)
        ctx["professional_name"] = appt.professional.name if appt.professional else ""
        ctx.pop("selected_date", None)
        ctx.pop("slot_start_at", None)
        ctx["is_rescheduling"] = True   # flag para confirmando.py bifurcar para reschedule
        session.context = ctx
        session.state   = STATE_REAGENDANDO
        start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)