"""Handler do estado INICIO — identificação do cliente e menu principal."""
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import BotSession
from app.modules.booking.engine import BookingEngine
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import first_name
from app.modules.whatsapp.session import reset_session
from app.modules.customers import service as customer_svc
from app.core.config import settings

booking_engine = BookingEngine()


STATE_AGUARDANDO_NOME   = "AGUARDANDO_NOME"
STATE_OFERTA_RECORRENTE = "OFERTA_RECORRENTE"
STATE_HUMANO            = "HUMANO"
STATE_MENU_PRINCIPAL    = "MENU_PRINCIPAL"


def handle(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str,
    user_input: str,
    start_escolhendo_servico,
    handle_ver_agendamentos,
    resolve_input,
) -> None:
    ctx = session.context or {}

    if not ctx.get("customer_id"):
        _identify_customer(
            db, session, company_id, whatsapp_id, instance, company_name,
            start_escolhendo_servico, handle_ver_agendamentos,
        )
        return

    last_list = ctx.get("last_list", [])

    if last_list:
        payload = resolve_input(user_input, last_list)

        if not payload:
            sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
            return

        if payload == "opt_agendar":
            ctx["last_list"] = []
            session.context = ctx
            start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
            return

        if payload == "opt_ver_agendamentos":
            ctx["last_list"] = []
            session.context = ctx
            handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
            return

        if payload == "opt_humano":
            session.state = STATE_HUMANO
            sender.send_text(instance, whatsapp_id, messages.HUMANO_CHAMADO)
            return

        # fallback seguro
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO)
        return

    # Sem lista ativa → mostra menu
    session.state = STATE_MENU_PRINCIPAL
    show_menu_principal(
        session, ctx, instance, whatsapp_id,
        company_name, ctx.get("customer_name")
    )


def _identify_customer(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str,
    start_escolhendo_servico,
    handle_ver_agendamentos,
) -> None:
    phone = whatsapp_id.split("@")[0]
    customer = customer_svc.get_by_phone(db, company_id, phone)

    # ─── Cliente novo ─────────────────────────────────────────────────────────
    if not customer:
        session.state = STATE_AGUARDANDO_NOME

        ctx = session.context or {}
        ctx["company_name"] = company_name
        session.context = ctx

        sender.send_text(
            instance,
            whatsapp_id,
            messages.boas_vindas_novo(company_name),
        )
        return

    # ─── Cliente existente ────────────────────────────────────────────────────
    ctx = dict(session.context or {})
    ctx["customer_id"]   = str(customer.id)
    ctx["customer_name"] = customer.name
    ctx["company_name"]  = company_name
    # FIX: removido ctx["booking_url"] — link não é enviado pelo bot

    appointments = booking_engine.get_customer_appointments(
        db, company_id, customer.id
    )

    if appointments:
        session.context = ctx
        show_menu_principal(
            session, ctx, instance, whatsapp_id, company_name, customer.name
        )
        return

    # ─── Oferta preditiva ─────────────────────────────────────────────────────
    offer = booking_engine.get_predictive_offer(
        db,
        company_id,
        customer.id,
        offer_ttl_minutes=settings.BOT_PREDICTIVE_OFFER_TTL_MINUTES,
    )

    if offer:
        nome       = first_name(customer.name)
        slot_label = offer.next_slot.strftime("%d/%m às %H:%M")

        ctx["predicted_slot"] = {
            "start_at":          offer.next_slot.isoformat(),
            "service_id":        str(offer.service_id),
            "service_name":      offer.service_name,
            "professional_id":   str(offer.professional_id),
            "professional_name": offer.professional_name,
            "expires_at":        offer.expires_at.isoformat(),
        }
        ctx["last_list"] = [
            {"row_id": "opt_confirmar_oferta", "payload": "opt_confirmar_oferta",
             "title": f"✅ Sim, {slot_label}"},
            {"row_id": "opt_outro_horario", "payload": "opt_outro_horario",
             "title": "🕐 Outro horário"},
            {"row_id": "opt_outro_servico", "payload": "opt_outro_servico",
             "title": "🔁 Outro serviço"},
        ]

        session.context = ctx
        session.state   = STATE_OFERTA_RECORRENTE

        text = messages.oferta_recorrente(
            nome,
            offer.service_name,
            offer.professional_name,
            slot_label,
            settings.BOT_PREDICTIVE_OFFER_TTL_MINUTES,
        )

        buttons = [
            {
                "buttonId": "opt_confirmar_oferta",
                "buttonText": {"displayText": f"✅ Sim, {slot_label}"},
            },
            {
                "buttonId": "opt_outro_horario",
                "buttonText": {"displayText": "🕐 Outro horário"},
            },
            {
                "buttonId": "opt_outro_servico",
                "buttonText": {"displayText": "🔁 Outro serviço"},
            },
        ]

        sender.send_buttons(instance, whatsapp_id, text, buttons)
        return

    # ─── Fallback → menu padrão ───────────────────────────────────────────────
    ctx["last_list"] = []
    session.context = ctx

    show_menu_principal(
        session, ctx, instance, whatsapp_id, company_name, customer.name
    )


def show_menu_principal(
    session: BotSession, ctx: dict,
    instance: str, to: str, company_name: str, name: Optional[str],
) -> None:
    nome = first_name(name) if name else ""

    # FIX: sempre usa menu sem link — _resolve_booking_url e
    # menu_principal_com_link removidos; link local nunca é enviado ao cliente
    text = messages.menu_principal(nome)

    ctx["last_list"] = [
        {"row_id": "opt_agendar",          "payload": "opt_agendar",
         "title": "📅 Agendar horário"},
        {"row_id": "opt_ver_agendamentos", "payload": "opt_ver_agendamentos",
         "title": "🗓 Ver seus agendamentos"},
        {"row_id": "opt_humano",           "payload": "opt_humano",
         "title": "💬 Falar com seu barbeiro"},
    ]

    session.context = ctx
    session.state = STATE_MENU_PRINCIPAL

    buttons = [
        {"buttonId": "opt_agendar",          "buttonText": {"displayText": "📅 Agendar horário"}},
        {"buttonId": "opt_ver_agendamentos", "buttonText": {"displayText": "🗓 Ver seus agendamentos"}},
        {"buttonId": "opt_humano",           "buttonText": {"displayText": "💬 Falar com seu barbeiro"}},
    ]

    sender.send_buttons(instance, to, text, buttons)