"""
Bot de agendamento via WhatsApp — máquina de estados.

Fluxo: INICIO → AGUARDANDO_NOME → ESCOLHENDO_SERVICO → ESCOLHENDO_PROFISSIONAL
       → ESCOLHENDO_HORARIO → ESCOLHENDO_DATA → CONFIRMANDO → (INICIO)
       ├── VER_AGENDAMENTOS → GERENCIANDO_AGENDAMENTO → REAGENDANDO
       └── HUMANO

Regras críticas implementadas:
  - SELECT FOR UPDATE na sessão (previne race condition de mensagens simultâneas)
  - last_message_id para idempotência de webhook (Evolution API re-entrega)
  - expires_at resetado a cada mensagem (TTL de 30 minutos)
  - Defense-in-depth: disponibilidade re-validada no CONFIRMANDO
  - user_id=None em create/cancel/reschedule (bot não tem User no DB)
"""
import asyncio
import logging
import uuid as uuidlib
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.infrastructure.db.models import BotSession, WhatsAppConnection
from app.infrastructure.db.models import Company, CompanySettings
from app.modules.whatsapp import evolution_client
from app.modules.customers import service as customer_svc
from app.modules.professionals import service as professional_svc
from app.modules.services import service as service_svc
from app.modules.appointments import service as appointment_svc
from app.modules.appointments.schemas import AppointmentCreate
from app.modules.availability import service as availability_svc

logger = logging.getLogger(__name__)

# TTL de sessão (em minutos) — resetado a cada mensagem recebida
SESSION_TTL_MINUTES = 30

# Estados
STATE_INICIO                  = "INICIO"
STATE_AGUARDANDO_NOME         = "AGUARDANDO_NOME"
STATE_OFERTA_RECORRENTE       = "OFERTA_RECORRENTE"
STATE_ESCOLHENDO_SERVICO      = "ESCOLHENDO_SERVICO"
STATE_ESCOLHENDO_PROFISSIONAL = "ESCOLHENDO_PROFISSIONAL"
STATE_ESCOLHENDO_HORARIO      = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA         = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO             = "CONFIRMANDO"
STATE_VER_AGENDAMENTOS        = "VER_AGENDAMENTOS"
STATE_GERENCIANDO_AGENDAMENTO = "GERENCIANDO_AGENDAMENTO"
STATE_REAGENDANDO             = "REAGENDANDO"
STATE_HUMANO                  = "HUMANO"


# ────────────────────────────────���───────────────────────────��────────────────
# Helpers de sessão
# ─────────────────────────────────────────────────────────────────────────────

def _get_session_locked(db: Session, company_id: UUID, whatsapp_id: str) -> BotSession:
    """
    Busca ou cria a sessão com SELECT FOR UPDATE NOWAIT.
    Levanta OperationalError se a linha já estiver bloqueada (mensagem sendo processada).
    """
    session = (
        db.query(BotSession)
        .filter(
            BotSession.company_id == company_id,
            BotSession.whatsapp_id == whatsapp_id,
        )
        .with_for_update(nowait=True)
        .first()
    )
    if not session:
        session = BotSession(
            company_id=company_id,
            whatsapp_id=whatsapp_id,
            state=STATE_INICIO,
            context={},
        )
        db.add(session)
        db.flush()
    return session


def _reset_session(session: BotSession, keep_customer: bool = True) -> None:
    """Reseta o contexto para o estado inicial, opcionalmente preservando dados do cliente."""
    ctx = session.context or {}
    new_ctx = {}
    if keep_customer:
        for key in ("customer_id", "customer_name", "is_recurring"):
            if key in ctx:
                new_ctx[key] = ctx[key]
    session.context = new_ctx
    session.state = STATE_INICIO


def _save_session(db: Session, session: BotSession) -> None:
    session.expires_at = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TTL_MINUTES)
    db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Resolução de input do usuário
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_input(user_input: str, last_list: list) -> Optional[str]:
    """
    Resolve o payload correspondente ao input do usuário.
    Aceita: row_id exato (Evolution lista/botão) ou input numérico ("1", "2"…).
    Retorna None se não encontrado (→ fallback).
    """
    if not last_list:
        return None
    cleaned = (user_input or "").strip()
    # Match direto por row_id
    for item in last_list:
        if item.get("row_id") == cleaned:
            return item.get("payload")
    # Match numérico ("1" → índice 0)
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(last_list):
            return last_list[idx].get("payload")
    return None


def _extract_user_text(data: dict) -> str:
    """Extrai texto da mensagem da Evolution API (texto, botão ou lista)."""
    msg = data.get("message") or {}
    # Mensagem de lista
    list_resp = msg.get("listResponseMessage", {})
    if list_resp:
        return list_resp.get("singleSelectReply", {}).get("selectedRowId", "")
    # Mensagem de botão
    btn_resp = msg.get("buttonsResponseMessage", {})
    if btn_resp:
        return btn_resp.get("selectedButtonId", "")
    # Texto puro
    return msg.get("conversation", "") or msg.get("extendedTextMessage", {}).get("text", "")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de envio
# ─────────────────────────────────────────────────────────────────────────────

def _send_text(instance: str, to: str, text: str) -> None:
    try:
        evolution_client.send_text(instance, to, text)
    except Exception as e:
        logger.error("send_text failed to=%s: %s", to, e)


def _send_buttons(instance: str, to: str, text: str, buttons: list[dict]) -> None:
    try:
        evolution_client.send_buttons(instance, to, text, buttons)
    except Exception as e:
        logger.error("send_buttons failed to=%s: %s", to, e)


def _send_list(instance: str, to: str, title: str, description: str, rows: list[dict]) -> None:
    try:
        evolution_client.send_list(instance, to, title, description, "Ver opções", rows)
    except Exception as e:
        logger.error("send_list failed to=%s: %s", to, e)


# ─────────────────────────────────────────────────────────────────────────────
# Handlers por estado
# ─────────────────────────────────────────────────────────────────────────────

def _handle_inicio(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, company_name: str,
) -> None:
    ctx = session.context or {}

    # Menu já foi mostrado — processa escolha 1/2/3
    if ctx.get("menu_shown"):
        last_list = ctx.get("last_list", [])
        payload = _resolve_input(ctx.get("_pending_input", ""), last_list)
        if payload == "opt_agendar":
            ctx["menu_shown"] = False
            session.context = ctx
            _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
            return
        elif payload == "opt_ver":
            ctx["menu_shown"] = False
            session.context = ctx
            session.state = STATE_VER_AGENDAMENTOS
            _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
            return
        elif payload == "opt_humano":
            session.state = STATE_HUMANO
            _send_text(instance, whatsapp_id,
                       "Vou chamar um atendente. Aguarde um momento… ☎️")
            return
        else:
            _send_menu_principal(instance, whatsapp_id, company_name, ctx.get("customer_name"))
            return

    # ── Identificação do cliente ──────────────────────────────────────────
    customer = customer_svc.get_by_phone(db, company_id, whatsapp_id)

    if not customer:
        # Novo cliente: pede nome
        session.state = STATE_AGUARDANDO_NOME
        _send_text(instance, whatsapp_id,
                   f"Olá! 👋 Bem-vindo à {company_name}!\n\nPara começar, qual é o seu nome?")
        return

    ctx["customer_id"] = str(customer.id)
    ctx["customer_name"] = customer.name

    # Verifica se é cliente recorrente
    last_completed = appointment_svc.list_completed_by_client(db, company_id, customer.id, limit=1)
    if last_completed:
        ctx["is_recurring"] = True
        last_appt = last_completed[0]
        # Tenta encontrar o próximo slot disponível com o mesmo combo
        svc_id = last_appt.services[0].service_id if last_appt.services else None
        prof_id = last_appt.professional_id
        predicted = None
        if svc_id and prof_id:
            slots = availability_svc.get_next_available_slots(
                db, company_id, prof_id, svc_id, days=7, limit=1
            )
            if slots:
                svc_name = last_appt.services[0].service_name
                prof_name = last_appt.professional.name if last_appt.professional else "Profissional"
                expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
                predicted = {
                    "start_at": slots[0].start_at.isoformat(),
                    "service_id": str(svc_id),
                    "service_name": svc_name,
                    "professional_id": str(prof_id),
                    "professional_name": prof_name,
                    "expires_at": expires_at.isoformat(),
                }

        if predicted:
            ctx["predicted_slot"] = predicted
            session.context = ctx
            session.state = STATE_OFERTA_RECORRENTE
            start_dt = datetime.fromisoformat(predicted["start_at"])
            slot_label = start_dt.strftime("%d/%m às %H:%M")
            text = (
                f"Olá, {customer.name}! Tudo beleza? 👋\n\n"
                f"Tenho um *{predicted['service_name']}* com *{predicted['professional_name']}* "
                f"disponível para *{slot_label}* 🕒\n\n"
                f"Reservado para você pelos próximos 5 minutos."
            )
            buttons = [
                {"buttonId": "opt_confirmar_oferta", "buttonText": {"displayText": f"✅ Sim, agendar para {slot_label}"}},
                {"buttonId": "opt_outro_horario",    "buttonText": {"displayText": "Escolher outro horário"}},
                {"buttonId": "opt_outro_servico",    "buttonText": {"displayText": "Outro serviço"}},
            ]
            ctx["last_list"] = [
                {"row_id": "opt_confirmar_oferta", "payload": "opt_confirmar_oferta"},
                {"row_id": "opt_outro_horario",    "payload": "opt_outro_horario"},
                {"row_id": "opt_outro_servico",    "payload": "opt_outro_servico"},
            ]
            session.context = ctx
            _send_buttons(instance, whatsapp_id, text, buttons)
            return

    # Menu padrão (cliente sem histórico ou sem slot preditivo)
    _send_menu_principal(instance, whatsapp_id, company_name, customer.name)
    ctx["menu_shown"] = True
    ctx["last_list"] = [
        {"row_id": "opt_1", "payload": "opt_agendar"},
        {"row_id": "opt_2", "payload": "opt_ver"},
        {"row_id": "opt_3", "payload": "opt_humano"},
    ]
    session.context = ctx


def _send_menu_principal(instance: str, to: str, company_name: str, name: Optional[str]) -> None:
    greeting = f"Olá, {name}! 😊" if name else f"Olá! 👋 Bem-vindo à {company_name}!"
    text = f"{greeting}\n\nO que você deseja fazer?"
    buttons = [
        {"buttonId": "opt_1", "buttonText": {"displayText": "📅 Agendar horário"}},
        {"buttonId": "opt_2", "buttonText": {"displayText": "🔍 Ver meus agendamentos"}},
        {"buttonId": "opt_3", "buttonText": {"displayText": "💬 Falar com atendente"}},
    ]
    evolution_client.send_buttons(instance, to, text, buttons)


def _handle_aguardando_nome(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    nome = user_input.strip()
    if len(nome) < 2:
        _send_text(instance, whatsapp_id, "Por favor, informe seu nome completo.")
        return

    customer = customer_svc.get_or_create_by_phone(db, company_id, whatsapp_id, nome)
    ctx = session.context or {}
    ctx["customer_id"] = str(customer.id)
    ctx["customer_name"] = customer.name
    ctx["is_recurring"] = False
    session.context = ctx
    _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)


def _handle_oferta_recorrente(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    last_list = ctx.get("last_list", [])
    payload = _resolve_input(user_input, last_list)
    predicted = ctx.get("predicted_slot")

    if not payload:
        _send_text(instance, whatsapp_id, "Ops! 😅 Escolha uma das opções acima.")
        return

    # Verifica expiração da oferta
    if predicted and payload == "opt_confirmar_oferta":
        expires = datetime.fromisoformat(predicted["expires_at"])
        if datetime.now(timezone.utc) > expires:
            _send_text(instance, whatsapp_id,
                       "⏰ A oferta expirou. Veja outros horários disponíveis.")
            ctx["service_id"] = predicted["service_id"]
            ctx["service_name"] = predicted["service_name"]
            ctx["professional_id"] = predicted["professional_id"]
            ctx["professional_name"] = predicted["professional_name"]
            ctx.pop("predicted_slot", None)
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return

        # Pré-preenche contexto com o slot preditivo e vai para CONFIRMANDO
        ctx["service_id"] = predicted["service_id"]
        ctx["service_name"] = predicted["service_name"]
        ctx["professional_id"] = predicted["professional_id"]
        ctx["professional_name"] = predicted["professional_name"]
        ctx["slot_start_at"] = predicted["start_at"]
        ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
        ctx.pop("predicted_slot", None)
        session.context = ctx
        session.state = STATE_CONFIRMANDO
        _send_confirmacao_resumo(instance, whatsapp_id, ctx)
        return

    if payload == "opt_outro_horario" and predicted:
        ctx["service_id"] = predicted["service_id"]
        ctx["service_name"] = predicted["service_name"]
        ctx["professional_id"] = predicted["professional_id"]
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

    _send_text(instance, whatsapp_id, "Ops! Escolha uma das opções.")


def _start_escolhendo_servico(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    services = service_svc.list_services(db, company_id, active_only=True)
    if not services:
        _send_text(instance, whatsapp_id, "Desculpe, não há serviços disponíveis no momento.")
        _reset_session(session)
        return

    rows = [{"rowId": f"opt_{i}", "title": s.name,
             "description": f"R$ {s.price:.2f} · {s.duration}min"}
            for i, s in enumerate(services)]

    ctx = session.context or {}
    ctx["last_list"] = [
        {"row_id": f"opt_{i}", "payload": str(s.id), "label": s.name}
        for i, s in enumerate(services)
    ]
    ctx["_service_map"] = {str(s.id): s.name for s in services}
    session.context = ctx
    session.state = STATE_ESCOLHENDO_SERVICO

    _send_list(instance, whatsapp_id, "Qual serviço deseja?", "Escolha um serviço:", rows)


def _handle_escolhendo_servico(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
    if not payload:
        _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    service = service_svc.get_service_or_404(db, company_id, UUID(payload))
    ctx["service_id"] = payload
    ctx["service_name"] = service.name
    session.context = ctx

    # Lista profissionais que oferecem este serviço
    professionals = professional_svc.list_by_service(db, company_id, UUID(payload))
    rows = [{"rowId": f"opt_{i}", "title": p.name, "description": ""} for i, p in enumerate(professionals)]
    # Opção "qualquer disponível"
    rows.append({"rowId": "opt_any", "title": "Qualquer disponível", "description": ""})

    ctx["last_list"] = (
        [{"row_id": f"opt_{i}", "payload": str(p.id), "label": p.name} for i, p in enumerate(professionals)]
        + [{"row_id": "opt_any", "payload": "any", "label": "Qualquer disponível"}]
    )
    session.context = ctx
    session.state = STATE_ESCOLHENDO_PROFISSIONAL

    _send_list(instance, whatsapp_id, "Com quem deseja agendar?", "Escolha o profissional:", rows)


def _handle_escolhendo_profissional(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))
    if not payload:
        _start_escolhendo_servico(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "any":
        ctx["professional_id"] = None
        ctx["professional_name"] = "Qualquer disponível"
    else:
        prof = professional_svc.get_professional_or_404(db, company_id, UUID(payload))
        ctx["professional_id"] = payload
        ctx["professional_name"] = prof.name

    session.context = ctx
    _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)


def _start_escolhendo_horario(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
) -> None:
    ctx = session.context or {}
    service_id = UUID(ctx["service_id"])
    prof_id_raw = ctx.get("professional_id")
    date_str = ctx.get("date")

    if date_str:
        # Data já escolhida — busca slots do dia
        target_date = datetime.fromisoformat(date_str).date()
        # Para "qualquer disponível", iteramos pelos profissionais
        slots = []
        if prof_id_raw:
            slots = availability_svc.get_available_slots(
                db, company_id, UUID(prof_id_raw), service_id, target_date
            )
        else:
            for p in professional_svc.list_by_service(db, company_id, service_id):
                s = availability_svc.get_available_slots(db, company_id, p.id, service_id, target_date)
                slots.extend(s)
                if len(slots) >= 6:
                    break
    else:
        # Sem data — próximos slots disponíveis
        slots = []
        if prof_id_raw:
            slots = availability_svc.get_next_available_slots(
                db, company_id, UUID(prof_id_raw), service_id, days=7, limit=6
            )
        else:
            for p in professional_svc.list_by_service(db, company_id, service_id):
                s = availability_svc.get_next_available_slots(
                    db, company_id, p.id, service_id, days=7, limit=3
                )
                slots.extend(s)
                if len(slots) >= 6:
                    break

    if not slots:
        _send_text(instance, whatsapp_id,
                   "😔 Não há horários disponíveis nos próximos dias. Tente outra data.")
        ctx["last_list"] = [{"row_id": "opt_outra_data", "payload": "outra_data"}]
        session.context = ctx
        session.state = STATE_ESCOLHENDO_HORARIO
        return

    rows = [{"rowId": f"slot_{i}",
             "title": s.start_at.strftime("%d/%m %H:%M"),
             "description": f"{s.professional_name}"}
            for i, s in enumerate(slots)]
    rows.append({"rowId": "opt_outra_data", "title": "📅 Outra data", "description": ""})

    # Payload codifica "start_at|professional_id" para que, quando o usuário
    # escolheu "Qualquer disponível", o professional_id correto seja resolvido
    # ao selecionar o slot, antes de chegar ao CONFIRMANDO.
    ctx["last_list"] = (
        [{"row_id": f"slot_{i}",
          "payload": f"{s.start_at.isoformat()}|{s.professional_id}",
          "label": s.start_at.strftime("%d/%m %H:%M")}
         for i, s in enumerate(slots)]
        + [{"row_id": "opt_outra_data", "payload": "outra_data"}]
    )
    session.context = ctx
    session.state = STATE_ESCOLHENDO_HORARIO
    _send_list(instance, whatsapp_id, "Horários disponíveis", "Escolha um horário:", rows)


def _handle_escolhendo_horario(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "outra_data":
        session.state = STATE_ESCOLHENDO_DATA
        _send_escolher_data(instance, whatsapp_id, ctx, session)
        return

    # Payload codificado como "start_at|professional_id" (ver _start_escolhendo_horario)
    if "|" in payload:
        start_str, prof_id_str = payload.split("|", 1)
        ctx["slot_start_at"] = start_str
        # Se o usuário escolheu "qualquer disponível", resolve o profissional real agora
        if not ctx.get("professional_id"):
            ctx["professional_id"] = prof_id_str
    else:
        ctx["slot_start_at"] = payload

    ctx["booking_idempotency_key"] = str(uuidlib.uuid4())
    session.context = ctx
    session.state = STATE_CONFIRMANDO
    _send_confirmacao_resumo(instance, whatsapp_id, ctx)


def _send_escolher_data(instance: str, whatsapp_id: str, ctx: dict, session: BotSession) -> None:
    today = datetime.now(timezone.utc).date()
    days = []
    offset = 0
    while len(days) < 4:
        d = today + timedelta(days=offset)
        days.append(d)
        offset += 1

    rows = []
    last_list = []
    for i, d in enumerate(days):
        label = "Hoje" if d == today else d.strftime("%A %d/%m").capitalize()
        row_id = f"opt_dia_{i}"
        rows.append({"rowId": row_id, "title": label, "description": ""})
        last_list.append({"row_id": row_id, "payload": d.isoformat(), "label": label})

    ctx["last_list"] = last_list
    session.context = ctx
    evolution_client.send_list(
        instance_name=instance,
        to=whatsapp_id,
        title="Para qual dia?",
        description="Escolha a data:",
        button_text="Ver datas",
        rows=rows,
    )


def _handle_escolhendo_data(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        _send_escolher_data(instance, whatsapp_id, ctx, session)
        return

    ctx["date"] = payload
    session.context = ctx
    _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)


def _send_confirmacao_resumo(instance: str, whatsapp_id: str, ctx: dict) -> None:
    slot_dt = datetime.fromisoformat(ctx["slot_start_at"])
    slot_label = slot_dt.strftime("%d/%m/%Y às %H:%M")
    text = (
        f"Confirme seu agendamento:\n\n"
        f"✂️ Serviço: *{ctx.get('service_name', '—')}*\n"
        f"👤 Profissional: *{ctx.get('professional_name', '—')}*\n"
        f"📅 Data/Hora: *{slot_label}*\n\n"
        f"Deseja confirmar?"
    )
    buttons = [
        {"buttonId": "opt_confirmar",       "buttonText": {"displayText": "✅ Confirmar"}},
        {"buttonId": "opt_alterar_horario", "buttonText": {"displayText": "🕐 Alterar horário"}},
        {"buttonId": "opt_cancelar",        "buttonText": {"displayText": "❌ Cancelar"}},
    ]
    evolution_client.send_buttons(instance, whatsapp_id, text, buttons)


def _handle_confirmando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    last_list = [
        {"row_id": "opt_confirmar",       "payload": "opt_confirmar"},
        {"row_id": "opt_alterar_horario", "payload": "opt_alterar_horario"},
        {"row_id": "opt_cancelar",        "payload": "opt_cancelar"},
    ]
    payload = _resolve_input(user_input, last_list)

    if payload == "opt_alterar_horario":
        ctx.pop("slot_start_at", None)
        ctx.pop("date", None)
        session.context = ctx
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "opt_cancelar":
        _reset_session(session)
        _send_text(instance, whatsapp_id, "Tudo bem! Se precisar, é só chamar. 😊")
        return

    if payload != "opt_confirmar":
        _send_confirmacao_resumo(instance, whatsapp_id, ctx)
        return

    # ── Confirmar agendamento ──────────────────────────────────────────────
    start_at = datetime.fromisoformat(ctx["slot_start_at"])
    idempotency_key = ctx.get("booking_idempotency_key") or str(uuidlib.uuid4())

    # Segurança: professional_id deve estar resolvido neste ponto
    professional_id_raw = ctx.get("professional_id")
    if not professional_id_raw:
        logger.error("CONFIRMANDO sem professional_id no context — whatsapp_id=%s", whatsapp_id)
        _send_text(instance, whatsapp_id, "❌ Erro interno ao confirmar. Tente novamente.")
        _reset_session(session)
        return

    data = AppointmentCreate(
        professional_id=UUID(professional_id_raw),
        client_id=UUID(ctx["customer_id"]),
        services=[{"service_id": UUID(ctx["service_id"])}],
        start_at=start_at,
        idempotency_key=idempotency_key,
    )

    try:
        appointment_svc.create_appointment(db, company_id, data, user_id=None)
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status == 409:
            # Slot tomado por outro — busca próximos
            _send_text(instance, whatsapp_id,
                       "😬 Desculpe, esse horário acabou de ser ocupado. Veja os próximos disponíveis:")
            ctx.pop("slot_start_at", None)
            ctx.pop("date", None)
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return
        logger.exception("create_appointment failed")
        _send_text(instance, whatsapp_id,
                   "❌ Ocorreu um erro ao criar o agendamento. Tente novamente.")
        return

    slot_label = start_at.strftime("%d/%m às %H:%M")
    _send_text(instance, whatsapp_id,
               f"✅ Agendamento confirmado!\n\n"
               f"✂️ {ctx.get('service_name')} com {ctx.get('professional_name')}\n"
               f"📅 {slot_label}\n\n"
               f"Te esperamos! 💈\n"
               f"⚠️ Cancelamento ou reagendamento até 2h antes.")

    _reset_session(session)


def _handle_ver_agendamentos(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str,
) -> None:
    ctx = session.context or {}
    customer_id = UUID(ctx["customer_id"])
    appointments = appointment_svc.list_active_by_client(db, company_id, customer_id)

    if not appointments:
        _send_text(instance, whatsapp_id,
                   "😅 Você não tem agendamentos ativos.\n\nDigite *1* para agendar.")
        ctx["last_list"] = [{"row_id": "opt_1", "payload": "opt_agendar"}]
        session.context = ctx
        session.state = STATE_INICIO
        ctx["menu_shown"] = False
        return

    rows = []
    last_list = []
    for i, a in enumerate(appointments):
        label = (
            f"{a.start_at.strftime('%d/%m %H:%M')} — "
            f"{a.services[0].service_name if a.services else '?'} "
            f"({a.professional.name if a.professional else '?'})"
        )
        rows.append({"rowId": f"appt_{i}", "title": label, "description": a.status})
        last_list.append({
            "row_id": f"appt_{i}",
            "payload": str(a.id),
            "label": label,
        })

    rows.append({"rowId": "opt_voltar", "title": "← Voltar", "description": ""})
    last_list.append({"row_id": "opt_voltar", "payload": "voltar"})

    ctx["last_list"] = last_list
    session.context = ctx
    session.state = STATE_VER_AGENDAMENTOS
    _send_list(instance, whatsapp_id, "Seus agendamentos", "Clique para gerenciar:", rows)


def _handle_ver_agendamentos_input(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if payload == "voltar" or not payload:
        _reset_session(session)
        return

    # payload é o appointment_id
    try:
        appt = appointment_svc.get_appointment_or_404(db, company_id, UUID(payload))
    except Exception:
        _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return

    ctx["managing_appointment_id"] = payload
    session.context = ctx
    session.state = STATE_GERENCIANDO_AGENDAMENTO

    can_reschedule = (appt.start_at - datetime.now(timezone.utc)) > timedelta(hours=2)
    slot_label = appt.start_at.strftime("%d/%m às %H:%M")
    text = f"Agendamento: {slot_label}\nStatus: {appt.status}\n\nO que deseja fazer?"

    buttons = []
    last_list = []
    if can_reschedule:
        buttons.append({"buttonId": "opt_reagendar", "buttonText": {"displayText": "🔄 Reagendar"}})
        last_list.append({"row_id": "opt_reagendar", "payload": "opt_reagendar"})
    buttons.append({"buttonId": "opt_cancelar_appt", "buttonText": {"displayText": "❌ Cancelar"}})
    buttons.append({"buttonId": "opt_voltar",        "buttonText": {"displayText": "← Voltar"}})
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
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if payload == "voltar":
        session.state = STATE_VER_AGENDAMENTOS
        _handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)
        return

    if payload == "opt_cancelar_appt":
        appt_id = UUID(ctx["managing_appointment_id"])
        try:
            appointment_svc.cancel_appointment(
                db, company_id, appt_id, user_id=None, reason="Cancelado via WhatsApp"
            )
            _send_text(instance, whatsapp_id, "✅ Agendamento cancelado com sucesso.")
        except Exception:
            _send_text(instance, whatsapp_id, "❌ Não foi possível cancelar. Tente novamente.")
        _reset_session(session)
        return

    if payload == "opt_reagendar":
        appt_id = UUID(ctx["managing_appointment_id"])
        try:
            appt = appointment_svc.get_appointment_or_404(db, company_id, appt_id)
        except Exception:
            _reset_session(session)
            return

        if (appt.start_at - datetime.now(timezone.utc)) <= timedelta(hours=2):
            _send_text(instance, whatsapp_id,
                       "😬 O prazo para reagendamento já passou (mínimo 2h antes).\n"
                       "Você pode apenas confirmar presença ou cancelar.")
            return

        # Preenche service/professional do agendamento existente para buscar slots
        if appt.services:
            ctx["service_id"] = str(appt.services[0].service_id)
            ctx["service_name"] = appt.services[0].service_name
        ctx["professional_id"] = str(appt.professional_id)
        ctx["professional_name"] = appt.professional.name if appt.professional else ""
        session.context = ctx
        session.state = STATE_REAGENDANDO
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    # Input inválido
    _send_text(instance, whatsapp_id, "Ops! Escolha uma das opções.")


def _handle_reagendando(
    db: Session, session: BotSession, company_id: UUID,
    whatsapp_id: str, instance: str, user_input: str,
) -> None:
    ctx = session.context or {}
    payload = _resolve_input(user_input, ctx.get("last_list", []))

    if not payload:
        _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
        return

    if payload == "outra_data":
        session.state = STATE_ESCOLHENDO_DATA
        _send_escolher_data(instance, whatsapp_id, ctx, session)
        return

    # Decode "start_at|professional_id" se necessário
    if "|" in payload:
        start_str, prof_id_str = payload.split("|", 1)
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
        slot_label = new_start.strftime("%d/%m às %H:%M")
        _send_text(instance, whatsapp_id,
                   f"✅ Agendamento remarcado para *{slot_label}*!\nTe esperamos! 💈")
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status == 409:
            _send_text(instance, whatsapp_id,
                       "😬 Esse horário acabou de ser ocupado. Escolha outro:")
            ctx.pop("slot_start_at", None)
            ctx.pop("date", None)
            session.context = ctx
            _start_escolhendo_horario(db, session, company_id, instance, whatsapp_id)
            return
        _send_text(instance, whatsapp_id, "❌ Erro ao remarcar. Tente novamente.")

    _reset_session(session)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — recebe mensagem do webhook
# ─────────────────────────────────────────────────────────────────────────────

async def handle_inbound_message(db: Session, instance_name: str, data: dict) -> None:
    """
    Ponto de entrada chamado pelo router quando chega um evento messages.upsert.
    Roteamento: instance_name → company_id → sessão do usuário.
    """
    # Ignora mensagens enviadas pelo próprio bot (fromMe=True)
    key = data.get("key", {})
    if key.get("fromMe"):
        return

    message_id = key.get("id", "")
    remote_jid = key.get("remoteJid", "")
    if not remote_jid:
        return

    # Normaliza número: "5511999999999@s.whatsapp.net" → "5511999999999"
    whatsapp_id = remote_jid.split("@")[0]

    # Resolve company_id pelo instance_name
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.instance_name == instance_name
    ).first()
    if not conn:
        logger.warning("webhook: instance_name=%s not found", instance_name)
        return

    company_id = conn.company_id

    # Verifica se bot está habilitado para esta empresa
    settings = db.query(CompanySettings).filter(
        CompanySettings.company_id == company_id
    ).first()
    if not settings or not settings.bot_enabled:
        return

    # Busca nome da empresa para mensagens de boas-vindas
    company = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Barbearia"

    # Extrai texto do usuário
    user_input = _extract_user_text(data)

    # Tenta obter sessão com lock
    try:
        session = _get_session_locked(db, company_id, whatsapp_id)
    except OperationalError:
        logger.debug("session locked, skipping message_id=%s", message_id)
        return

    # Idempotência: ignora re-entrega da mesma mensagem
    if message_id and session.last_message_id == message_id:
        logger.debug("duplicate message_id=%s, skipping", message_id)
        _save_session(db, session)
        return
    session.last_message_id = message_id

    # Sessão expirada → reseta
    if session.expires_at and datetime.now(timezone.utc) > session.expires_at.replace(tzinfo=timezone.utc):
        _reset_session(session, keep_customer=False)

    state = session.state

    try:
        if state in (STATE_INICIO, STATE_OFERTA_RECORRENTE) and state == STATE_INICIO:
            # Guarda input para uso dentro de _handle_inicio quando menu já foi mostrado
            ctx = session.context or {}
            ctx["_pending_input"] = user_input
            session.context = ctx
            _handle_inicio(db, session, company_id, whatsapp_id, instance_name, company_name)

        elif state == STATE_AGUARDANDO_NOME:
            _handle_aguardando_nome(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_OFERTA_RECORRENTE:
            _handle_oferta_recorrente(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_ESCOLHENDO_SERVICO:
            _handle_escolhendo_servico(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_ESCOLHENDO_PROFISSIONAL:
            _handle_escolhendo_profissional(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_ESCOLHENDO_HORARIO:
            _handle_escolhendo_horario(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_ESCOLHENDO_DATA:
            _handle_escolhendo_data(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_CONFIRMANDO:
            _handle_confirmando(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_VER_AGENDAMENTOS:
            _handle_ver_agendamentos_input(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_GERENCIANDO_AGENDAMENTO:
            _handle_gerenciando_agendamento(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_REAGENDANDO:
            _handle_reagendando(db, session, company_id, whatsapp_id, instance_name, user_input)

        elif state == STATE_HUMANO:
            # Bot silenciado — não responde
            pass

        else:
            # Estado desconhecido → reseta
            logger.warning("unknown state=%s, resetting", state)
            _reset_session(session, keep_customer=False)

    except Exception:
        logger.exception("bot error state=%s whatsapp_id=%s", state, whatsapp_id)
        _send_text(instance_name, whatsapp_id,
                   "Ops! 😅 Ocorreu um erro. Tente novamente em instantes.")

    _save_session(db, session)
