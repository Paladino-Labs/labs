"""
Bot de agendamento via WhatsApp — máquina de estados.
 
Fluxo:
  INICIO → [AGUARDANDO_NOME] → [OFERTA_RECORRENTE]
         → ESCOLHENDO_SERVICO → ESCOLHENDO_PROFISSIONAL
         → ESCOLHENDO_HORARIO → [ESCOLHENDO_DATA] → ESCOLHENDO_HORARIO
         → CONFIRMANDO → INICIO (reset)
  INICIO → VER_AGENDAMENTOS → GERENCIANDO_AGENDAMENTO
         → CANCELANDO | REAGENDANDO
 
Regras críticas:
  - SELECT FOR UPDATE NOWAIT (previne race condition de mensagens simultâneas)
  - last_message_id para idempotência de webhook (Evolution API re-entrega)
  - expires_at TTL de 30 min, resetado a cada mensagem
  - Disponibilidade re-validada no CONFIRMANDO (defense-in-depth)
  - user_id=None em create/cancel/reschedule (bot não tem User no DB)
"""
import logging
import uuid as uuidlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID
 
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
 
from app.infrastructure.db.models import BotSession, WhatsAppConnection
from app.infrastructure.db.models import Company, CompanySettings
from app.modules.booking.engine import BookingEngine
from app.modules.whatsapp import evolution_client
from app.modules.whatsapp import messages
from app.modules.whatsapp.session import get_session_locked, save_session, reset_session
from app.modules.customers import service as customer_svc
from app.modules.professionals import service as professional_svc
from app.modules.services import service as service_svc
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.schemas import AppointmentCreate
from app.modules.availability import service as availability_svc
from app.core.config import settings
from app.modules.appointments.polices import PolicyViolationError

booking_engine = BookingEngine()
logger = logging.getLogger(__name__)
 
# ─── Estados ──────────────────────────────────────────────────────────────────
STATE_INICIO                  = "INICIO"
STATE_AGUARDANDO_NOME         = "AGUARDANDO_NOME"
STATE_CONFIRMAR_NOME          = "CONFIRMAR_NOME"
STATE_OFERTA_RECORRENTE       = "OFERTA_RECORRENTE"
STATE_MENU_PRINCIPAL          = "MENU_PRINCIPAL"
STATE_ESCOLHENDO_SERVICO      = "ESCOLHENDO_SERVICO"
STATE_ESCOLHENDO_PROFISSIONAL = "ESCOLHENDO_PROFISSIONAL"
STATE_ESCOLHENDO_HORARIO      = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA         = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO             = "CONFIRMANDO"
STATE_VER_AGENDAMENTOS        = "VER_AGENDAMENTOS"
STATE_GERENCIANDO_AGENDAMENTO = "GERENCIANDO_AGENDAMENTO"
STATE_CANCELANDO              = "CANCELANDO"
STATE_REAGENDANDO             = "REAGENDANDO"
STATE_HUMANO                  = "HUMANO"
 
_DIAS_PT = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
 
 
# ─── Normalização de input ────────────────────────────────────────────────────
 
def _resolve_input(user_input: str, last_list: list) -> Optional[str]:
    """
    Resolve payload pelo input do usuário.
    Aceita: row_id exato (botão/lista Evolution) ou número ("1", "2"...).
    Retorna None se não encontrado → fallback.
    """
    if not last_list:
        return None
    cleaned = (user_input or "").strip()
    for item in last_list:
        if item.get("row_id") == cleaned:
            return item.get("payload")
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(last_list):
            return last_list[idx].get("payload")
    return None
 
 
def _extract_user_text(data: dict) -> str:
    """Extrai texto da mensagem da Evolution API (texto, botão ou lista)."""
    msg = data.get("message") or {}
    list_resp = msg.get("listResponseMessage", {})
    if list_resp:
        selected_id = list_resp.get("singleSelectReply", {}).get("selectedRowId", "")
        if selected_id:
            return selected_id
    btn_resp = msg.get("buttonsResponseMessage", {})
    if btn_resp:
        return btn_resp.get("selectedButtonId", "")
    return msg.get("conversation", "") or msg.get("extendedTextMessage", {}).get("text", "")
 
 
def _is_universal_command(text: str) -> Optional[str]:
    """Detecta comandos globais independente do estado atual."""
    t = (text or "").strip().lower()
    if t in ("0", "menu", "início", "inicio", "voltar", "sair", "cancelar"):
        return "menu"
    if t in ("ver agendamentos", "meus agendamentos", "agendamentos"):
        return "ver_agendamentos"
    if t in ("atendente", "humano", "ajuda", "suporte"):
        return "humano"
    return None
 
 
# ─── Helpers de envio ─────────────────────────────────────────────────────────
 
def _send_text(instance: str, to: str, text: str) -> None:
    try:
        evolution_client.send_text(instance, to, text)
    except Exception as e:
        logger.error("send_text failed to=%s: %s", to, e)
 
 
def _send_buttons(instance: str, to: str, text: str, buttons: list[dict]) -> None:
    """Envia botões interativos com fallback para texto numerado."""
    try:
        evolution_client.send_buttons(instance, to, text, buttons)
    except Exception as e:
        logger.warning("send_buttons falhou, fallback texto. to=%s: %s", to, e)
        lines = [text, ""]
        for i, btn in enumerate(buttons, start=1):
            label = btn.get("buttonText", {}).get("displayText", str(i))
            lines.append(f"*{i}.* {label}")
        lines.append("\n_Digite o número da opção._")
        _send_text(instance, to, "\n".join(lines))
 
 
def _send_list(instance: str, to: str, title: str, description: str, rows: list[dict]) -> None:
    """Envia lista interativa com fallback para texto numerado."""
    try:
        evolution_client.send_list(instance, to, title, description, "Ver opções", rows)
    except Exception as e:
        logger.warning("send_list falhou, fallback texto. to=%s: %s", to, e)
        _send_list_as_text(instance, to, title, description, rows)
 
 
def _send_list_as_text(instance: str, to: str, title: str, description: str, rows: list[dict]) -> None:
    lines = [f"*{title}*"]
    if description:
        lines.append(description)
    lines.append("")
    for i, row in enumerate(rows, start=1):
        label = row.get("title", str(i))
        desc  = row.get("description", "")
        lines.append(f"*{i}.* {label}" + (f" — {desc}" if desc else ""))
    lines.append("\n_Digite o número da opção._")
    _send_text(instance, to, "\n".join(lines))
 
 
# ─── Utilitários de formatação ────────────────────────────────────────────────
 
def _label_date(d) -> str:
    """Formata data com label contextual em português."""
    today = datetime.now(timezone.utc).date()
    if d == today:
        return f"Hoje ({d.strftime('%d/%m')})"
    if d == today + timedelta(days=1):
        return f"Amanhã ({d.strftime('%d/%m')})"
    weekday = _DIAS_PT[d.weekday()]
    return f"{weekday} ({d.strftime('%d/%m')})"
 
 
def _first_name(full_name: str) -> str:
    """Retorna o primeiro nome para uso em mensagens."""
    return (full_name or "").strip().split()[0] if full_name else ""
 
 
# ─── INICIO ───────────────────────────────────────────────────────────────────
 
def _handle_inicio(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str,
    user_input: str, push_name: str = "",
) -> None:
    ctx = session.context or {}
 
    # Passo 1: cliente ainda não identificado → iniciar onboarding
    if not ctx.get("customer_id"):
        _identify_customer(db, session, company_id, whatsapp_id, instance,
                           company_name, push_name)
        return
 
    # Passo 2: menu já foi apresentado → processa escolha
    last_list = ctx.get("last_list", [])
    if last_list:
        payload = _resolve_input(user_input, last_list)
        if payload == "opt_agendar":
            ctx["last_list"] = []
            session.context = ctx
            _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
            return
        if payload == "opt_ver":
            ctx["last_list"] = []
            session.context = ctx
            _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
            return
        if payload == "opt_humano":
            session.state = STATE_HUMANO
            _send_text(instance, whatsapp_id, messages.HUMANO_CHAMADO)
            return
        # Input inválido → reenvia menu
        _show_menu_principal(session, ctx, instance, whatsapp_id, company_name,
                             ctx.get("customer_name"))
        return
 
    # Passo 3: menu ainda não foi apresentado → exibe
    _show_menu_principal(session, ctx, instance, whatsapp_id, company_name,
                         ctx.get("customer_name"))
 
 
def _identify_customer(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str, push_name: str = "",
) -> None:
    """
    Identifica o cliente pelo número de WhatsApp.
    Novo → pede nome. Recorrente → oferta preditiva ou menu padrão.
    """
    customer = customer_svc.get_by_phone(db, company_id, whatsapp_id)
 
    if not customer:
        # Cliente novo
        session.state = STATE_AGUARDANDO_NOME
        ctx = session.context or {}
        ctx["company_name"] = company_name
        if push_name:
            ctx["push_name_suggestion"] = push_name
        session.context = ctx
        _send_text(instance, whatsapp_id, messages.boas_vindas_novo(company_name))
        return
 
    # Cliente existente
    ctx = dict(session.context or {})
    ctx["customer_id"]   = str(customer.id)
    ctx["customer_name"] = customer.name
    ctx["company_name"]  = company_name

    appointments = booking_engine.get_customer_appointments(
        db, company_id, customer.id
    )

    if appointments:
        session.context = ctx
        _show_menu_principal(
             session, ctx, instance, whatsapp_id, company_name, customer.name
        )
        return
 
    # Tenta oferta preditiva
    offer = booking_engine.get_predictive_offer(
        db, company_id, customer.id, offer_ttl_minutes=5
    )
    if offer:
        ctx["predicted_slot"] = {
            "start_at": offer.next_slot.isoformat(),
            "service_id": str(offer.service_id),
            "service_name": offer.service_name,
            "professional_id": str(offer.professional_id),
            "professional_name": offer.professional_name,
            "expires_at": offer.expires_at.isoformat(),
        }
        ctx["last_list"] = [
            {"row_id": "opt_confirmar_oferta", "payload": "opt_confirmar_oferta"},
            {"row_id": "opt_outro_horario",    "payload": "opt_outro_horario"},
            {"row_id": "opt_outro_servico",    "payload": "opt_outro_servico"},
            {"row_id": "opt_ver_agendamentos", "payload": "opt_ver_agendamentos"},
        ]
     
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

        nome = _first_name(customer.name)
        slot_label = offer.next_slot.strftime("%d/%m às %H:%M")

        text = messages.oferta_recorrente(
            nome,
            offer.service_name,
            offer.professional_name,
            slot_label,
            5,
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

    _send_buttons(instance, whatsapp_id, text, buttons)
    return
 
    # Sem oferta preditiva → menu padrão
    ctx["last_list"] = []
    session.context = ctx
    _show_menu_principal(session, ctx, instance, whatsapp_id, company_name, customer.name)
 
 
def _show_menu_principal(
    session: BotSession, ctx: dict,
    instance: str, to: str, company_name: str, name: Optional[str],
) -> None:
    nome = _first_name(name) if name else ""
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
    _send_buttons(instance, to, text, buttons)
 
 
# ─── AGUARDANDO_NOME ──────────────────────────────────────────────────────────
 
def _handle_aguardando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    nome = user_input.strip()

    if len(nome) < 2:
        _send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    # NÃO salva ainda ❌
    # Guarda temporariamente
    ctx = dict(session.context or {})
    ctx["nome_temp"] = nome
    session.context = ctx

    # IMPORTANTE: mudar etapa
    session.state = STATE_CONFIRMAR_NOME

    # Envia confirmação
    _send_text(instance, whatsapp_id, messages.confirmar_nome(nome))


# ─── AGUARDANDO_NOME ──────────────────────────────────────────────────────────

def _handle_confirmando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    resposta = user_input.strip().lower()
    ctx = dict(session.context or {})

    nome_temp = ctx.get("nome_temp")

    if not nome_temp:
        # fallback de segurança
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        _send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    # ✅ CONFIRMOU
    if resposta in ["1", "sim", "s", "ok", "isso", "confirmar"]:
        customer = customer_svc.get_or_create_by_phone(
            db, company_id, whatsapp_id, nome_temp
        )

        ctx["customer_id"] = str(customer.id)
        ctx["customer_name"] = customer.name
        ctx.pop("nome_temp", None)
        session.context = ctx

        nome_curto = _first_name(customer.name)

        session.state = STATE_MENU_PRINCIPAL

        _send_text(instance, whatsapp_id, messages.boas_vindas_nome_confirmado(nome_curto))
        _send_text(instance, whatsapp_id, messages.menu_principal(nome_curto))
        return

    # 🔁 QUER CORRIGIR
    if resposta in ["2", "não", "nao", "n", "errado", "corrigir"]:
        session.state = STATE_AGUARDANDO_NOME
        session.context = ctx
        _send_text(instance, whatsapp_id, messages.PEDIR_NOME_NOVAMENTE)
        return

    # ❌ RESPOSTA INVÁLIDA
    _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
 
 
# ─── OFERTA_RECORRENTE ────────────────────────────────────────────────────────
 
def _handle_oferta_recorrente(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx       = dict(session.context or {})
    payload   = _resolve_input(user_input, ctx.get("last_list", []))
    predicted = ctx.get("predicted_slot")
 
    if not payload:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return
 
    if payload == "opt_confirmar_oferta" and predicted:
        expires = datetime.fromisoformat(predicted["expires_at"])
     
        if datetime.now(timezone.utc) > expires:
            _send_text(instance, whatsapp_id, messages.OFERTA_EXPIRADA)
         
            ctx["service_id"]        = predicted["service_id"]
            ctx["service_name"]      = predicted["service_name"]
            ctx["professional_id"]   = predicted["professional_id"]
            ctx["professional_name"] = predicted["professional_name"]
            ctx.pop("predicted_slot", None)
         
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return
 
        ctx["service_id"]            = predicted["service_id"]
        ctx["service_name"]          = predicted["service_name"]
        ctx["professional_id"]       = predicted["professional_id"]
        ctx["professional_name"]     = predicted["professional_name"]
        ctx["slot_start_at"]         = predicted["start_at"]
        ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
        ctx.pop("predicted_slot", None)
     
        session.context = ctx
        session.state = STATE_CONFIRMANDO
        _send_confirmacao_resumo(instance, whatsapp_id, ctx)
        return
 
    if payload == "opt_outro_horario" and predicted:
        ctx["service_id"]        = predicted["service_id"]
        ctx["service_name"]      = predicted["service_name"]
        ctx["professional_id"]   = predicted["professional_id"]
        ctx["professional_name"] = predicted["professional_name"]
        ctx.pop("predicted_slot", None)
     
        session.context = ctx
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
 
    if payload == "opt_outro_servico":
        ctx.pop("predicted_slot", None)
        session.context = ctx
        _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return
 
    _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)


# ─── ESCOLHENDO_SERVICO ───────────────────────────────────────────────────────

def _handle_menu_principal(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    payload = user_input.strip().lower()
    ctx = dict(session.context or {})

    # 📅 Agendar
    if payload == "opt_agendar":
        session.state = STATE_ESCOLHENDO_SERVICO
        session.context = ctx

        _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    # 🗓 Ver agendamentos
    if payload == "opt_ver":
        session.state = STATE_VER_AGENDAMENTOS
        session.context = ctx

        _handle_ver_agendamentos_input(
            db, session, company_id, whatsapp_id, instance, user_input
        )
        return

    # 💬 Humano
    if payload == "opt_humano":
        session.state = STATE_HUMANO
        session.context = ctx

        _send_text(instance, whatsapp_id, messages.HUMANO_CHAMADO)
        return

    # ❌ fallback (usuário digitou algo)
    _show_menu_principal(
        session, ctx, instance, whatsapp_id,
        ctx.get("company_name"), ctx.get("customer_name")
    )
 
 
# ─── ESCOLHENDO_SERVICO ───────────────────────────────────────────────────────
 
def _start_escolhendo_servico(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    services = service_svc.list_services(db, company_id, active_only=True)

    ctx = dict(session.context or {})

    if not services:
        text = messages.SEM_SERVICOS

        buttons = [
            {
                "buttonId": "opt_menu",
                "buttonText": {"displayText": "🏠 Menu principal"}
            },
            {
                "buttonId": "opt_humano",
                "buttonText": {"displayText": "💬 Falar com atendente"}
            },
        ]

        ctx["last_list"] = [
            {"row_id": "opt_menu", "payload": "opt_menu"},
            {"row_id": "opt_humano", "payload": "opt_humano"},
        ]

        session.context = ctx

        _send_buttons(instance, whatsapp_id, text, buttons)
        return

    rows = [
        {
            "rowId": str(s.id),
            "title": s.name,
            "description": f"R$ {s.price:.2f} · {s.duration} min"
        }
        for i, s in enumerate(services)
    ]

    ctx["last_list"] = [
        {"row_id": str(s.id), "payload": str(s.id)}
        for i, _ in enumerate(services)
    ]

    session.context = ctx
    session.state = STATE_ESCOLHENDO_SERVICO

    nome = _first_name(ctx.get("customer_name", ""))

    _send_list(
        instance, whatsapp_id,
        "✂️ Nossos serviços",
        messages.escolha_servico(nome),
        rows,
    )
 
 
def _handle_escolhendo_servico(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = dict(session.context or {})
    payload = _resolve_input(user_input, ctx.get("last_list", []))
    if not payload:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return
     
    try:
        service = service_svc.get_service_or_404(db, company_id, UUID(payload))
    except Exception:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return
 
    ctx["service_id"]   = payload
    ctx["service_name"] = service.name

    session.context = ctx

    _start_escolhendo_profissional(db, session, company_id, instance, whatsapp_id)
 
 
# ─── ESCOLHENDO_PROFISSIONAL ──────────────────────────────────────────────────
 
def _start_escolhendo_profissional(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    ctx = dict(session.context or {})

    service_id = UUID(ctx["service_id"])
    profs = professional_svc.list_by_service(db, company_id, service_id)

    if not profs:
        _send_text(
            instance,
            whatsapp_id,
            "😕 Não há profissionais disponíveis para esse serviço no momento."
        )
        return

    rows = [
        {"rowId": str(p.id), "title": p.name, "description": ""}
        for p in profs
    ]

    rows.append({
        "rowId": "prof_any",
        "title": "👥 Qualquer disponível",
        "description": ""
    })

    ctx["last_list"] = [
        {"row_id": str(p.id), "payload": str(p.id)}
        for p in profs
    ] + [
        {"row_id": "prof_any", "payload": "any"}
    ]

    session.context = ctx
    session.state = STATE_ESCOLHENDO_PROFISSIONAL

    svc = ctx.get("service_name", "")

    _send_list(
        instance, whatsapp_id,
        "👤 Escolha o profissional",
        messages.escolha_profissional(svc),
        rows,
    )
 
 
def _handle_escolhendo_profissional(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = dict(session.context or {})
    payload = _resolve_input(user_input, ctx.get("last_list", []))
    if not payload:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return
 
    if payload == "any":
        ctx["professional_id"]   = None
        ctx["professional_name"] = "Qualquer disponível"
    else:
        try:
            prof = professional_svc.get_professional_or_404(db, company_id, UUID(payload))
            ctx["professional_id"]   = payload
            ctx["professional_name"] = prof.name
        except Exception:
            _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
            return
 
    session.context = ctx
    _send_escolher_data(db, session, company_id, instance, whatsapp_id)
 
 
# ─── ESCOLHENDO_DATA ──────────────────────────────────────────────────────────
 
def _send_escolher_data(
    instance: str, whatsapp_id: str, ctx: dict, session: BotSession
) -> None:
    today = datetime.now(timezone.utc).date()
    candidate_days = [today + timedelta(days=i) for i in range(7)]

    rows, last_list = [], []

    for d in candidate_days:
        row_id = d.isoformat()
        label  = _label_date(d)

        rows.append({
            "rowId": row_id,
            "title": label,
            "description": ""
        })

        last_list.append({
            "row_id": row_id,
            "payload": row_id
        })

    ctx = dict(ctx)
    ctx["last_list"] = last_list

    session.context = ctx
    session.state = STATE_ESCOLHENDO_DATA

    nome = _first_name(ctx.get("customer_name", ""))
    svc  = ctx.get("service_name", "")
    prof = ctx.get("professional_name", "")

    _send_list(
        instance, whatsapp_id,
        messages.escolha_data_titulo(svc),
        messages.escolha_data_descricao(nome, prof),
        rows,
    )
 

def _handle_escolhendo_data(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = dict(session.context or {})
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["selected_date"] = payload
    session.context = ctx

    _start_escolhendo_horario(
        db, session, company_id, instance, whatsapp_id
    )

 
# ─── ESCOLHENDO_HORARIO ───────────────────────────────────────────────────────
 
def _start_escolhendo_horario(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    ctx = dict(session.context or {})

    svc_id   = UUID(ctx["service_id"])
    prof_raw = ctx.get("professional_id")
    date_str = ctx.get("selected_date")

    if date_str:
        target_date = datetime.fromisoformat(date_str).date()
        slots = []

        if prof_raw:
            slots = availability_svc.get_available_slots(
                db, company_id, UUID(prof_raw), svc_id, target_date
            )
        else:
            for p in professional_svc.list_by_service(db, company_id, svc_id):
                slots.extend(
                    availability_svc.get_available_slots(
                        db, company_id, p.id, svc_id, target_date
                    )
                )
                if len(slots) >= settings.BOT_MAX_SLOTS_DISPLAYED:
                    break
    else:
        slots = []

        if prof_raw:
            slots = availability_svc.get_next_available_slots(
                db, company_id, UUID(prof_raw), svc_id,
                days=7, limit=settings.BOT_MAX_SLOTS_DISPLAYED,
            )
        else:
            half = max(1, settings.BOT_MAX_SLOTS_DISPLAYED // 2)
            for p in professional_svc.list_by_service(db, company_id, svc_id):
                slots.extend(
                    availability_svc.get_next_available_slots(
                        db, company_id, p.id, svc_id, days=7, limit=half
                    )
                )
                if len(slots) >= settings.BOT_MAX_SLOTS_DISPLAYED:
                    break

    # 🔥 ordena sempre
    slots.sort(key=lambda s: s.start_at)
    slots = slots[:settings.BOT_MAX_SLOTS_DISPLAYED]

    any_prof = (prof_raw is None)

    if not slots:
        _send_buttons(
            instance,
            whatsapp_id,
            messages.SEM_HORARIOS,
            [
                {"buttonId": "opt_outra_data", "buttonText": {"displayText": "📅 Escolher outra data"}},
                {"buttonId": "opt_menu", "buttonText": {"displayText": "🏠 Menu principal"}},
            ]
        )

        ctx["last_list"] = [
            {"row_id": "opt_outra_data", "payload": "outra_data"},
            {"row_id": "opt_menu", "payload": "opt_menu"},
        ]

        session.context = ctx
        session.state = STATE_ESCOLHENDO_HORARIO
        return

    rows, last_list = [], []

    for s in slots:
        time_label = s.start_at.strftime("%H:%M")

        row_id = f"{s.start_at.isoformat()}|{s.professional_id}"

        rows.append({
            "rowId": row_id,
            "title": time_label,
            "description": s.professional_name if any_prof else ""
        })

        last_list.append({
            "row_id": row_id,
            "payload": row_id,
        })

    rows.append({
        "rowId": "opt_outra_data",
        "title": "📅 Escolher outra data",
        "description": ""
    })

    last_list.append({
        "row_id": "opt_outra_data",
        "payload": "outra_data"
    })

    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_ESCOLHENDO_HORARIO

    prof_label = ctx.get("professional_name", "")

    _send_list(
        instance, whatsapp_id,
        "🕐 Horários disponíveis",
        messages.escolha_horario(ctx["service_name"], prof_label),
        rows,
    )
 
 
def _handle_escolhendo_horario(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = dict(session.context or {})
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    if payload == "outra_data":
        session.state = STATE_ESCOLHENDO_DATA
        _send_escolher_data(instance, whatsapp_id, ctx, session)
        return

    if "|" in payload:
        try:
            start_str, prof_id_str = payload.split("|", 1)
        except ValueError:
            _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
            return

        ctx["slot_start_at"] = start_str

        # resolve profissional se veio de "qualquer disponível"
        if not ctx.get("professional_id"):
            ctx["professional_id"] = prof_id_str
            try:
                prof = professional_svc.get_professional_or_404(
                    db, company_id, UUID(prof_id_str)
                )
                ctx["professional_name"] = prof.name
            except Exception:
                pass
    else:
        _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    ctx["booking_idempotency_key"] = str(uuidlib.uuid4())

    session.context = ctx
    session.state = STATE_CONFIRMANDO

    _send_confirmacao_resumo(instance, whatsapp_id, ctx)
 
 
# ─── CONFIRMANDO ──────────────────────────────────────────────────────────────
 
_CONFIRMANDO_LIST = [
    {"row_id": "opt_confirmar",       "payload": "opt_confirmar"},
    {"row_id": "opt_alterar_horario", "payload": "opt_alterar_horario"},
    {"row_id": "opt_cancelar",        "payload": "opt_cancelar"},
]
 
 
def _send_confirmacao_resumo(instance: str, whatsapp_id: str, ctx: dict) -> None:
    slot_dt    = datetime.fromisoformat(ctx["slot_start_at"])
    date_label = slot_dt.strftime("%d/%m/%Y")
    time_label = slot_dt.strftime("%H:%M")
    prof_label = ctx.get("professional_name") or "—"

    text = messages.confirmacao_resumo(
        ctx.get("service_name", "—"), prof_label, date_label, time_label
    )
    buttons = [
        {"buttonId": "opt_confirmar",
         "buttonText": {"displayText": "✅ Confirmar"}},
        {"buttonId": "opt_alterar_horario",
         "buttonText": {"displayText": "🕐 Alterar horário"}},
        {"buttonId": "opt_cancelar",
         "buttonText": {"displayText": "❌ Cancelar"}},
    ]
    _send_buttons(instance, whatsapp_id, text, buttons)
 
 
def _handle_confirmando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = session.context or {}
    payload = _resolve_input(user_input, _CONFIRMANDO_LIST)
 
    if payload == "opt_alterar_horario":
        ctx.pop("slot_start_at", None)
        ctx.pop("selected_date", None)
        session.context = ctx
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
 
    if payload == "opt_cancelar":
        nome = _first_name(ctx.get("customer_name", ""))
        reset_session(session)
        _send_text(instance, whatsapp_id, messages.cancelamento_pelo_usuario(nome))
        return
 
    if payload != "opt_confirmar":
        _send_confirmacao_resumo(instance, whatsapp_id, ctx)
        return
 
    # ── Criar agendamento ─────────────────────────────────────────────────────
    start_at    = datetime.fromisoformat(ctx["slot_start_at"])
    idem_key    = ctx.get("booking_idempotency_key") or str(uuidlib.uuid4())
    prof_id_raw = ctx.get("professional_id")
    customer_id = ctx.get("customer_id")
 
    if not prof_id_raw or not customer_id:
        logger.error("CONFIRMANDO: dados incompletos ctx=%s whatsapp_id=%s", ctx, whatsapp_id)
        _send_text(instance, whatsapp_id, messages.ERRO_DADOS_INCOMPLETOS)
        reset_session(session)
        return
 
    appt_data = AppointmentCreate(
        professional_id=UUID(prof_id_raw),
        client_id=UUID(customer_id),
        services=[{"service_id": UUID(ctx["service_id"])}],
        start_at=start_at,
        idempotency_key=idem_key,
    )
    try:
        appointment_svc.create_appointment(db, company_id, appt_data, user_id=None)
    except Exception as e:
        if getattr(e, "status_code", None) == 409:
            _send_text(instance, whatsapp_id, messages.HORARIO_OCUPADO_CONFIRMANDO)
            ctx.pop("slot_start_at", None)
            ctx.pop("selected_date", None)
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return
        logger.exception("create_appointment failed whatsapp_id=%s", whatsapp_id)
        _send_text(instance, whatsapp_id, messages.ERRO_CONFIRMAR_AGENDAMENTO)
        return
 
    nome       = _first_name(ctx.get("customer_name", ""))
    slot_label = start_at.strftime("%d/%m às %H:%M")
    _send_text(
        instance, whatsapp_id,
        messages.agendamento_confirmado(
            nome,
            ctx.get("service_name", ""),
            ctx.get("professional_name", ""),
            slot_label,
            settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
        ),
    )
    reset_session(session)
 
 
# ─── VER_AGENDAMENTOS ─────────────────────────────────────────────────────────
 
def _handle_ver_agendamentos(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    ctx         = session.context or {}
    customer_id = ctx.get("customer_id")
    if not customer_id:
        reset_session(session)
        return
 
    appointments = appointment_svc.list_active_by_client(db, company_id, UUID(customer_id))
    nome = _first_name(ctx.get("customer_name", ""))
 
    if not appointments:
        _send_text(instance, whatsapp_id, messages.sem_agendamentos_ativos(nome))
        ctx["last_list"] = [{"row_id": "opt_agendar", "payload": "opt_agendar"}]
        session.context = ctx
        session.state = STATE_INICIO
        return
 
    rows, last_list = [], []
    for i, a in enumerate(appointments):
        svc_name   = a.services[0].service_name if a.services else "Serviço"
        prof_name  = a.professional.name if a.professional else "?"
        date_label = a.start_at.strftime("%d/%m")
        time_label = a.start_at.strftime("%H:%M")
        title  = f"{date_label} às {time_label} — {svc_name}"
        desc   = f"com {prof_name}"
        row_id = f"appt_{i}"
        rows.append({"rowId": row_id, "title": title, "description": desc})
        last_list.append({"row_id": row_id, "payload": str(a.id)})
 
    rows.append({"rowId": "opt_voltar", "title": "← Voltar ao menu", "description": ""})
    last_list.append({"row_id": "opt_voltar", "payload": "voltar"})
 
    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_VER_AGENDAMENTOS
 
    _send_list(
        instance, whatsapp_id,
        "📋 Seus agendamentos",
        messages.lista_agendamentos_descricao(nome),
        rows,
    )
 
 
def _handle_ver_agendamentos_input(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
 
    if payload == "voltar" or not payload:
        reset_session(session)
        ctx2 = session.context or {}
        _show_menu_principal(session, ctx2, instance, whatsapp_id,
                             ctx2.get("company_name", ""), ctx2.get("customer_name"))
        return
 
    try:
        appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(payload))
    except Exception:
        _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return
 
    ctx["managing_appointment_id"] = payload
    session.context = ctx
    _start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)
 
 
# ─── GERENCIANDO_AGENDAMENTO ──────────────────────────────────────────────────
 
def _start_gerenciando_agendamento(
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
 
    text = messages.gerenciar_agendamento(svc_name, prof_name, slot_label)
    buttons   = []
    last_list = []
 
    if can_change:
        buttons.append({"buttonId": "opt_reagendar",
                        "buttonText": {"displayText": "🔄 Reagendar"}})
        last_list.append({"row_id": "opt_reagendar", "payload": "opt_reagendar"})
 
    buttons.append({"buttonId": "opt_cancelar_appt",
                    "buttonText": {"displayText": "❌ Cancelar agendamento"}})
    buttons.append({"buttonId": "opt_voltar",
                    "buttonText": {"displayText": "← Voltar"}})
    last_list += [
        {"row_id": "opt_cancelar_appt", "payload": "opt_cancelar_appt"},
        {"row_id": "opt_voltar",        "payload": "voltar"},
    ]
 
    ctx["last_list"] = last_list
    session.context = ctx
    _send_buttons(instance, whatsapp_id, text, buttons)
 
 
def _handle_gerenciando_agendamento(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
 
    if payload == "voltar":
        _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return
 
    if payload == "opt_cancelar_appt":
        session.state = STATE_CANCELANDO
        _start_cancelando(db, session, company_id, whatsapp_id, instance)
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
            _send_text(
                instance, whatsapp_id,
                messages.reagendamento_fora_prazo(settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE),
            )
            return
 
        if appt.services:
            ctx["service_id"]   = str(appt.services[0].service_id)
            ctx["service_name"] = appt.services[0].service_name
        ctx["professional_id"]   = str(appt.professional_id)
        ctx["professional_name"] = appt.professional.name if appt.professional else ""
        ctx.pop("selected_date", None)
        session.context = ctx
        session.state = STATE_REAGENDANDO
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
 
    _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
 
 
# ─── CANCELANDO ───────────────────────────────────────────────────────────────
 
def _start_cancelando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    ctx         = session.context or {}
    appt_id_str = ctx.get("managing_appointment_id")
    if not appt_id_str:
        reset_session(session)
        return
 
    try:
        appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(appt_id_str))
    except Exception:
        reset_session(session)
        return
 
    from app.modules.appointments.polices import check_cancellation_policy
    allowed, msg = check_cancellation_policy(
        start_at=appt.start_at,
        now=datetime.now(timezone.utc),
        min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
    )
    slot_label = appt.start_at.strftime("%d/%m às %H:%M")
 
    if not allowed:
        _send_text(instance, whatsapp_id, messages.cancelamento_fora_prazo(msg))
        _start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)
        return
 
    text = messages.confirmacao_cancelamento(slot_label)
    buttons = [
        {"buttonId": "opt_confirmar_cancel",
         "buttonText": {"displayText": "✅ Sim, cancelar"}},
        {"buttonId": "opt_voltar_gerenciando",
         "buttonText": {"displayText": "← Não, voltar"}},
    ]
    ctx["last_list"] = [
        {"row_id": "opt_confirmar_cancel",   "payload": "confirmar_cancel"},
        {"row_id": "opt_voltar_gerenciando", "payload": "voltar_gerenciando"},
    ]
    session.context = ctx
    _send_buttons(instance, whatsapp_id, text, buttons)
 
 
def _handle_cancelando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
 
    if payload == "voltar_gerenciando":
        appt_id_str = ctx.get("managing_appointment_id", "")
        try:
            appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(appt_id_str))
            _start_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance, appt)
        except Exception:
            reset_session(session)
        return
 
    if payload == "confirmar_cancel":
        appt_id_str = ctx.get("managing_appointment_id")
        if not appt_id_str:
            reset_session(session)
            return
        nome = _first_name(ctx.get("customer_name", ""))
        try:
            appointment_svc.cancel_appointment(
                db, company_id, UUID(appt_id_str),
                user_id=None, reason="Cancelado via WhatsApp",
            )
            _send_text(instance, whatsapp_id, messages.cancelamento_confirmado(nome))
        except PolicyViolationError as e:
            _send_text(instance, whatsapp_id, f"⚠️ {e.detail}")
        except Exception:
            logger.exception("cancel_appointment failed id=%s", appt_id_str)
            _send_text(instance, whatsapp_id, messages.ERRO_CANCELAR_AGENDAMENTO)
        reset_session(session)
        return
 
    _send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO)
 
 
# ─── REAGENDANDO ──────────────────────────────────────────────────────────────
 
def _handle_reagendando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx     = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
 
    if not payload:
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return
 
    if payload == "outra_data":
        session.state = STATE_ESCOLHENDO_DATA
        _send_escolher_data(instance, whatsapp_id, ctx, session)
        return
 
    if "|" in payload:
        start_str, _ = payload.split("|", 1)
        new_start = datetime.fromisoformat(start_str)
    else:
        new_start = datetime.fromisoformat(payload)
 
    appt_id = UUID(ctx["managing_appointment_id"])
    from app.modules.appointments.schemas import RescheduleRequest
    try:
        appointment_svc.reschedule_appointment(
            db, company_id, appt_id,
            RescheduleRequest(start_at=new_start),
            user_id=None,
        )
        nome       = _first_name(ctx.get("customer_name", ""))
        slot_label = new_start.strftime("%d/%m às %H:%M")
        _send_text(instance, whatsapp_id, messages.reagendamento_confirmado(nome, slot_label))
    except PolicyViolationError as e:
        _send_text(instance, whatsapp_id, f"⚠️ {e.detail}")
    except Exception as e:
        if getattr(e, "status_code", None) == 409:
            _send_text(instance, whatsapp_id, messages.HORARIO_OCUPADO_REAGENDANDO)
            ctx.pop("slot_start_at", None)
            ctx.pop("selected_date", None)
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return
        _send_text(instance, whatsapp_id, messages.ERRO_REAGENDAR_AGENDAMENTO)
 
    reset_session(session)
 
 
# ─── Entry point — webhook messages.upsert ────────────────────────────────────
 
async def handle_inbound_message(db: Session, instance_name: str, data: dict) -> None:
    """
    Ponto de entrada chamado pelo router quando chega um evento messages.upsert.
    Normaliza payload → identifica empresa → lock de sessão → roteamento por estado.
    """
    logger.info("handle_inbound: instance=%s keys=%s",
                instance_name, list(data.keys()) if isinstance(data, dict) else type(data).__name__)
 
    # Batch → flat (Evolution API v2 envolve mensagens em array)
    if isinstance(data, dict) and "messages" in data:
        messages_list = data.get("messages") or []
        if not messages_list:
            return
        data = messages_list[0]
 
    key = data.get("key", {})
    if key.get("fromMe"):
        return
 
    message_id = key.get("id", "")
    push_name  = data.get("pushName", "")
 
    # LID addressing mode (WhatsApp novo formato)
    addressing_mode = key.get("addressingMode", "")
    remote_jid_alt  = key.get("remoteJidAlt", "")
    raw_jid         = key.get("remoteJid", "")
    remote_jid = remote_jid_alt if (addressing_mode == "lid" and remote_jid_alt) else raw_jid
 
    if not remote_jid:
        logger.warning("sem remoteJid, instance=%s", instance_name)
        return
    if remote_jid.endswith("@g.us"):
        return  # ignora grupos silenciosamente
 
    whatsapp_id = remote_jid.split("@")[0]
 
    # Resolve empresa pelo instance_name
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.instance_name == instance_name
    ).first()
    if not conn:
        logger.warning("instance_name=%s não encontrado no DB", instance_name)
        return
 
    company_id = conn.company_id
 
    # Verifica se bot está ativo
    company_settings = db.query(CompanySettings).filter(
        CompanySettings.company_id == company_id
    ).first()
    if not company_settings or not company_settings.bot_enabled:
        return
 
    company = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Barbearia"
    user_input   = _extract_user_text(data)
 
    logger.info("whatsapp_id=%s msg_id=%s input=%r", whatsapp_id, message_id, user_input[:50])
 
    # Lock de sessão — previne processamento simultâneo do mesmo usuário
    try:
        session = get_session_locked(db, company_id, whatsapp_id)
    except OperationalError:
        logger.debug("session locked, descartando message_id=%s", message_id)
        return
 
    # Idempotência — descarta re-entrega da mesma mensagem
    if message_id and session.last_message_id == message_id:
        logger.debug("mensagem duplicada message_id=%s, ignorando", message_id)
        save_session(db, session)
        return
    session.last_message_id = message_id
 
    # Expiração de sessão
    if session.expires_at:
        exp = session.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            reset_session(session, keep_customer=False)
 
    state = session.state
 
    # ── Comandos universais (exceto AGUARDANDO_NOME e HUMANO) ─────────────────
    if state not in (STATE_AGUARDANDO_NOME, STATE_HUMANO):
        cmd = _is_universal_command(user_input)
        if cmd == "menu":
            reset_session(session)
            ctx = session.context or {}
            _show_menu_principal(session, ctx, instance_name, whatsapp_id,
                                 company_name, ctx.get("customer_name"))
            save_session(db, session)
            return
        if cmd == "ver_agendamentos":
            ctx = session.context or {}
            if ctx.get("customer_id"):
                _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance_name)
                save_session(db, session)
                return
        if cmd == "humano":
            session.state = STATE_HUMANO
            _send_text(instance_name, whatsapp_id, messages.HUMANO_CHAMADO)
            save_session(db, session)
            return
 
    # ── Dispatcher principal ──────────────────────────────────────────────────
    try:
        if state == STATE_INICIO:
            _handle_inicio(db, session, company_id, whatsapp_id, instance_name,
                           company_name, user_input, push_name)
 
        elif state == STATE_AGUARDANDO_NOME:
            _handle_aguardando_nome(db, session, company_id, whatsapp_id,
                                    instance_name, user_input)
 
        elif state == STATE_OFERTA_RECORRENTE:
            _handle_oferta_recorrente(db, session, company_id, whatsapp_id,
                                      instance_name, user_input)

        elif state == STATE_MENU_PRINCIPAL:
            _handle_menu_principal(
                                   db, session, company_id, whatsapp_id,
                                   instance_name, user_input
                                   )
 
        elif state == STATE_ESCOLHENDO_SERVICO:
            _handle_escolhendo_servico(db, session, company_id, whatsapp_id,
                                       instance_name, user_input)
 
        elif state == STATE_ESCOLHENDO_PROFISSIONAL:
            _handle_escolhendo_profissional(db, session, company_id, whatsapp_id,
                                            instance_name, user_input)
 
        elif state == STATE_ESCOLHENDO_HORARIO:
            _handle_escolhendo_horario(db, session, company_id, whatsapp_id,
                                       instance_name, user_input)
 
        elif state == STATE_ESCOLHENDO_DATA:
            _handle_escolhendo_data(db, session, company_id, whatsapp_id,
                                    instance_name, user_input)
 
        elif state == STATE_CONFIRMANDO:
            _handle_confirmando(db, session, company_id, whatsapp_id,
                                instance_name, user_input)
 
        elif state == STATE_VER_AGENDAMENTOS:
            _handle_ver_agendamentos_input(db, session, company_id, whatsapp_id,
                                           instance_name, user_input)
 
        elif state == STATE_GERENCIANDO_AGENDAMENTO:
            _handle_gerenciando_agendamento(db, session, company_id, whatsapp_id,
                                            instance_name, user_input)
 
        elif state == STATE_CANCELANDO:
            _handle_cancelando(db, session, company_id, whatsapp_id,
                               instance_name, user_input)
 
        elif state == STATE_REAGENDANDO:
            _handle_reagendando(db, session, company_id, whatsapp_id,
                                instance_name, user_input)
 
        elif state == STATE_HUMANO:
            pass  # Silêncio — atendente assume a conversa
 
        else:
            logger.warning("estado desconhecido state=%s, resetando sessão", state)
            reset_session(session, keep_customer=False)
 
    except Exception:
        logger.exception("bot error state=%s whatsapp_id=%s", state, whatsapp_id)
        _send_text(instance_name, whatsapp_id, messages.ERRO_GENERICO)

    try:
        save_session(db, session)
    except Exception:
        logger.exception("save_session error state=%s whatsapp_id=%s", state, whatsapp_id)

