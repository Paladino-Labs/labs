"""Handlers do estado VER_AGENDAMENTOS."""
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.appointments import service as appointment_svc
from app.modules.booking.engine import booking_engine

STATE_VER_AGENDAMENTOS = "VER_AGENDAMENTOS"
STATE_INICIO           = "INICIO"


def handle_ver_agendamentos(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    ctx         = session.context or {}
    customer_id = ctx.get("customer_id")
    if not customer_id:
        reset_session(session)
        return

    appointments = booking_engine.get_customer_appointments(db, company_id, UUID(customer_id))
    nome         = first_name(ctx.get("customer_name", ""))

    if not appointments:
        sender.send_text(instance, whatsapp_id, messages.sem_agendamentos_ativos(nome))
        ctx = dict(ctx)
        ctx["last_list"] = [{"row_id": "opt_agendar", "payload": "opt_agendar",
                              "title": "📅 Agendar horário"}]
        session.context  = ctx
        session.state    = STATE_INICIO
        return

    rows, last_list = [], []
    for i, a in enumerate(appointments):
        svc_name   = a.service_name
        prof_name  = a.professional_name
        date_label = a.start_at.strftime("%d/%m")
        time_label = a.start_at.strftime("%H:%M")
        row_id     = f"appt_{i}"
        rows.append({"rowId": row_id,
                     "title": f"{date_label} às {time_label} — {svc_name}",
                     "description": f"com {prof_name}"})
        title_str = f"{date_label} às {time_label} — {svc_name}"
        last_list.append({"row_id": row_id, "payload": str(a.id), "title": title_str})

    ctx = dict(ctx)
    ctx["last_list"] = last_list
    session.context  = ctx
    session.state    = STATE_VER_AGENDAMENTOS

    sender.send_list(instance, whatsapp_id, "📋 Seus agendamentos",
                     messages.lista_agendamentos_descricao(nome), rows)


def handle_input(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
    resolve_input,
    start_gerenciando_agendamento,
    show_menu_principal,
) -> None:
    ctx     = session.context or {}
    payload = resolve_input(user_input, ctx.get("last_list", []))

    if payload == "voltar" or not payload:
        reset_session(session)
        ctx2 = session.context or {}
        show_menu_principal(session, ctx2, instance, whatsapp_id,
                            ctx2.get("company_name", ""), ctx2.get("customer_name"))
        return

    try:
        appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(payload))
    except Exception:
        handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return

    ctx = dict(ctx)
    ctx["managing_appointment_id"] = payload
    session.context = ctx
    start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)