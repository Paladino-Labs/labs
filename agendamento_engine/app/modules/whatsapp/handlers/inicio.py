"""Handler do estado INICIO — identificação do cliente e menu principal."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.customers import service as customer_svc
from app.modules.appointments import service as appointment_svc
from app.modules.availability import service as availability_svc
from app.core.config import settings

STATE_AGUARDANDO_NOME   = "AGUARDANDO_NOME"
STATE_OFERTA_RECORRENTE = "OFERTA_RECORRENTE"
STATE_HUMANO            = "HUMANO"


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str,
    user_input: str, push_name: str,
    start_escolhendo_servico,
    handle_ver_agendamentos,
    resolve_input,
) -> None:
    ctx = session.context or {}

    if not ctx.get("customer_id"):
        _identify_customer(
            db, session, company_id, whatsapp_id, instance, company_name, push_name,
            start_escolhendo_servico, handle_ver_agendamentos,
        )
        return

    last_list = ctx.get("last_list", [])
    if last_list:
        payload = resolve_input(user_input, last_list)
        if payload == "opt_agendar":
            ctx["last_list"] = []
            session.context = ctx
            start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
            return
        if payload == "opt_ver":
            ctx["last_list"] = []
            session.context = ctx
            handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
            return
        if payload == "opt_humano":
            session.state = STATE_HUMANO
            sender.send_text(instance, whatsapp_id, messages.HUMANO_CHAMADO)
            return
        show_menu_principal(session, ctx, instance, whatsapp_id, company_name,
                            ctx.get("customer_name"))
        return

    show_menu_principal(session, ctx, instance, whatsapp_id, company_name,
                        ctx.get("customer_name"))


def _identify_customer(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str, push_name: str,
    start_escolhendo_servico,
    handle_ver_agendamentos,
) -> None:
    customer = customer_svc.get_by_phone(db, company_id, whatsapp_id)

    if not customer:
        session.state = STATE_AGUARDANDO_NOME
        ctx = session.context or {}
        ctx["company_name"] = company_name
        if push_name:
            ctx["push_name_suggestion"] = push_name
        session.context = ctx
        sender.send_text(instance, whatsapp_id, messages.boas_vindas_novo(company_name))
        return

    ctx = dict(session.context or {})
    ctx["customer_id"]   = str(customer.id)
    ctx["customer_name"] = customer.name
    ctx["company_name"]  = company_name

    upcoming = appointment_svc.list_upcoming_by_client(db, company_id, customer.id, limit=1)
    if upcoming:
        session.context = ctx
        show_menu_principal(session, ctx, instance, whatsapp_id, company_name, customer.name)
        return

    last_completed = appointment_svc.list_completed_by_client(db, company_id, customer.id, limit=1)
    if last_completed:
        last_appt = last_completed[0]
        svc_id  = last_appt.services[0].service_id if last_appt.services else None
        prof_id = last_appt.professional_id
        if svc_id and prof_id:
            slots = availability_svc.get_next_available_slots(
                db, company_id, prof_id, svc_id, days=7, limit=1
            )
            if slots:
                svc_name   = last_appt.services[0].service_name
                prof_name  = last_appt.professional.name if last_appt.professional else "Profissional"
                slot_dt    = slots[0].start_at
                slot_label = slot_dt.strftime("%d/%m às %H:%M")
                expires_at = datetime.now(timezone.utc) + timedelta(
                    minutes=settings.BOT_PREDICTIVE_OFFER_TTL_MINUTES
                )
                ctx["predicted_slot"] = {
                    "start_at":          slot_dt.isoformat(),
                    "service_id":        str(svc_id),
                    "service_name":      svc_name,
                    "professional_id":   str(prof_id),
                    "professional_name": prof_name,
                    "expires_at":        expires_at.isoformat(),
                }
                ctx["last_list"] = [
                    {"row_id": "opt_confirmar_oferta", "payload": "opt_confirmar_oferta"},
                    {"row_id": "opt_outro_horario",    "payload": "opt_outro_horario"},
                    {"row_id": "opt_outro_servico",    "payload": "opt_outro_servico"},
                ]
                session.context = ctx
                session.state = STATE_OFERTA_RECORRENTE

                nome = first_name(customer.name)
                text = messages.oferta_recorrente(
                    nome, svc_name, prof_name, slot_label,
                    settings.BOT_PREDICTIVE_OFFER_TTL_MINUTES,
                )
                buttons = [
                    {"buttonId": "opt_confirmar_oferta",
                     "buttonText": {"displayText": "✅ Sim, confirmar"}},
                    {"buttonId": "opt_outro_horario",
                     "buttonText": {"displayText": "🕐 Outro horário"}},
                    {"buttonId": "opt_outro_servico",
                     "buttonText": {"displayText": "🔁 Outro serviço"}},
                ]
                sender.send_buttons(instance, whatsapp_id, text, buttons)
                return

    ctx["last_list"] = []
    session.context = ctx
    show_menu_principal(session, ctx, instance, whatsapp_id, company_name, customer.name)


def show_menu_principal(
    session: BotSession, ctx: dict,
    instance: str, to: str, company_name: str, name: Optional[str],
) -> None:
    nome = first_name(name) if name else ""
    text = messages.menu_principal(nome)
    buttons = [
        {"buttonId": "opt_agendar", "buttonText": {"displayText": "📅 Agendar horário"}},
        {"buttonId": "opt_ver",     "buttonText": {"displayText": "🗓 Ver seus agendamentos"}},
        {"buttonId": "opt_humano",  "buttonText": {"displayText": "💬 Falar com seu barbeiro"}},
    ]
    ctx["last_list"] = [
        {"row_id": "opt_agendar", "payload": "opt_agendar"},
        {"row_id": "opt_ver",     "payload": "opt_ver"},
        {"row_id": "opt_humano",  "payload": "opt_humano"},
    ]
    session.context = ctx
    sender.send_buttons(instance, to, text, buttons)