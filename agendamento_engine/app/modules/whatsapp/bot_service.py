"""
Bot de agendamento via WhatsApp — máquina de estados.

Fluxo:
  INICIO → [AGUARDANDO_NOME] → [CONFIRMAR_NOME]
         → [OFERTA_RECORRENTE] | MENU_PRINCIPAL
         → ESCOLHENDO_SERVICO → ESCOLHENDO_PROFISSIONAL
         → ESCOLHENDO_DATA → ESCOLHENDO_TURNO → ESCOLHENDO_HORARIO
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
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.infrastructure.db.models import BotSession, WhatsAppConnection, Company, CompanySettings
from app.modules.whatsapp import messages
from app.modules.whatsapp import sender
from app.modules.whatsapp.helpers import extract_user_text, is_universal_command, resolve_input
from app.modules.whatsapp.session import get_session_locked, save_session, reset_session

from app.modules.whatsapp.handlers import inicio as h_inicio
from app.modules.whatsapp.handlers import aguardando_nome as h_nome
from app.modules.whatsapp.handlers import oferta_recorrente as h_oferta
from app.modules.whatsapp.handlers import menu_principal as h_menu
from app.modules.whatsapp.handlers import escolhendo_servico as h_servico
from app.modules.whatsapp.handlers import escolhendo_profissional as h_profissional
from app.modules.whatsapp.handlers import escolhendo_data as h_data
from app.modules.whatsapp.handlers import escolhendo_turno as h_turno
from app.modules.whatsapp.handlers import escolhendo_horario as h_horario
from app.modules.whatsapp.handlers import confirmando as h_confirmando
from app.modules.whatsapp.handlers import ver_agendamentos as h_ver
from app.modules.whatsapp.handlers import gerenciando_agendamento as h_gerenciando
from app.modules.whatsapp.handlers import cancelando as h_cancelando
from app.modules.whatsapp.handlers import reagendando as h_reagendando

logger = logging.getLogger(__name__)

# ─── Estados ──────────────────────────────────────────────────────────────────
STATE_INICIO                  = "INICIO"
STATE_AGUARDANDO_NOME         = "AGUARDANDO_NOME"
STATE_CONFIRMAR_NOME          = "CONFIRMAR_NOME"
STATE_OFERTA_RECORRENTE       = "OFERTA_RECORRENTE"
STATE_MENU_PRINCIPAL          = "MENU_PRINCIPAL"
STATE_ESCOLHENDO_SERVICO      = "ESCOLHENDO_SERVICO"
STATE_ESCOLHENDO_PROFISSIONAL = "ESCOLHENDO_PROFISSIONAL"
STATE_ESCOLHENDO_TURNO        = "ESCOLHENDO_TURNO"
STATE_ESCOLHENDO_HORARIO      = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA         = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO             = "CONFIRMANDO"
STATE_VER_AGENDAMENTOS        = "VER_AGENDAMENTOS"
STATE_GERENCIANDO_AGENDAMENTO = "GERENCIANDO_AGENDAMENTO"
STATE_CANCELANDO              = "CANCELANDO"
STATE_REAGENDANDO             = "REAGENDANDO"
STATE_HUMANO                  = "HUMANO"

# ── BookingEngine FSM — estados roteados pelo novo pipeline ───────────────────
# Importado de input_parser para evitar duplicação
from app.modules.whatsapp.input_parser import BOOKING_STATES  # noqa: E402


# ─── Wrappers locais (evitam repetir db/session nos handlers) ─────────────────
# Cada _start_* é uma função local que fecha sobre db/session/company_id,
# permitindo que os handlers a recebam como callable sem conhecer bot_service.

def _mk_start_servico(db, session, company_id):
    def _f(db_, sess_, cid_, inst_, wid_):
        h_servico.start(db_, sess_, cid_, inst_, wid_)
    return _f


def _start_escolhendo_servico(db: Session, session: BotSession, company_id: UUID,
                               instance: str, whatsapp_id: str) -> None:
    """
    Inicia o fluxo de agendamento via BookingEngine FSM.

    Cria uma BookingSession (channel="whatsapp"), inicializa com o cliente
    já identificado e envia a lista de serviços ao usuário.
    """
    from app.infrastructure.db.models.booking_session import BookingSession as _BookingSession
    from app.modules.booking.engine import booking_engine
    from app.modules.booking.schemas import SessionUpdateResult
    from app.modules.whatsapp.response_formatter import whatsapp_response_formatter

    ctx              = session.context or {}
    customer_id      = ctx.get("customer_id")
    customer_name    = ctx.get("customer_name", "")
    company_timezone = ctx.get("company_timezone", "America/Sao_Paulo")

    if not customer_id:
        logger.error("_start_escolhendo_servico: sem customer_id no contexto. whatsapp_id=%s", whatsapp_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        return

    # ── Cria BookingSession (IDLE) e inicializa com cliente já identificado ───
    booking_session = booking_engine.start_session(
        db, company_id,
        channel="whatsapp",
        company_timezone=company_timezone,
    )

    # Bypass de SET_CUSTOMER: cliente foi identificado pelo fluxo de INICIO.
    # Definir customer_id e estado diretamente evita segundo round-trip ao banco
    # e o problema do LID addressing mode (whatsapp_id não é telefone real).
    from uuid import UUID as _UUID
    booking_session.customer_id = _UUID(customer_id)
    booking_session.state = "AWAITING_SERVICE"

    # ── Lista serviços e persiste no contexto da BookingSession ───────────────
    options = booking_engine.list_services(db, company_id)
    booking_session.context = {
        "customer_name":         customer_name,
        "last_listed_services": [
            {
                "id":               str(o.id),
                "name":             o.name,
                "price":            str(o.price),
                "duration_minutes": o.duration_minutes,
                "row_key":          o.row_key,
            }
            for o in options
        ],
    }

    # ── Vincula BookingSession à BotSession via contexto ─────────────────────
    ctx2 = dict(ctx)
    ctx2["booking_session_id"] = str(booking_session.id)
    session.context = ctx2
    session.state   = "AWAITING_SERVICE"

    # ── Envia lista de serviços ───────────────────────────────────────────────
    result = SessionUpdateResult(next_state="AWAITING_SERVICE", options=options)
    whatsapp_response_formatter.format_and_send(
        result, instance, whatsapp_id,
        booking_session.context, company_timezone,
    )


def _start_escolhendo_profissional(db: Session, session: BotSession, company_id: UUID,
                                    instance: str, whatsapp_id: str) -> None:
    h_profissional.start(db, session, company_id, instance, whatsapp_id,
                         send_escolher_data=_send_escolher_data)


def _send_escolher_data(
    db: Session, session: BotSession, company_id: UUID,
    instance: str, whatsapp_id: str,
    *args, **kwargs
) -> None:
    h_data.send_escolher_data(db, session, company_id, instance, whatsapp_id)


def _start_escolhendo_turno(db: Session, session: BotSession, company_id: UUID,
                             instance: str, whatsapp_id: str) -> None:
    h_turno.send_escolher_turno(db, session, company_id, instance, whatsapp_id)


def _start_escolhendo_horario(db: Session, session: BotSession, company_id: UUID,
                               instance: str, whatsapp_id: str) -> None:
    h_horario.start(db, session, company_id, instance, whatsapp_id,
                    send_escolher_data=_send_escolher_data,
                    send_confirmacao_resumo=h_confirmando.send_resumo)


def _handle_ver_agendamentos(db: Session, session: BotSession, company_id: UUID,
                              whatsapp_id: str, instance: str) -> None:
    h_ver.handle_ver_agendamentos(db, session, company_id, whatsapp_id, instance)


def _start_gerenciando_agendamento(db: Session, session: BotSession, company_id: UUID,
                                    whatsapp_id: str, instance: str, appt) -> None:
    h_gerenciando.start(db, session, company_id, whatsapp_id, instance, appt)


def _start_cancelando(db: Session, session: BotSession, company_id: UUID,
                      whatsapp_id: str, instance: str) -> None:
    h_cancelando.start(db, session, company_id, whatsapp_id, instance,
                       start_gerenciando_agendamento=_start_gerenciando_agendamento)


def _handle_booking_state(
    db: Session,
    session: BotSession,
    company_id: UUID,
    instance: str,
    whatsapp_id: str,
    user_input: str,
    company_timezone: str,
) -> None:
    """
    Handler unificado para os estados de agendamento roteados pelo BookingEngine.

    Fluxo:
      1. Carrega BookingSession pelo ID armazenado no contexto da BotSession
      2. Parseia o input do usuário → (BookingAction, payload)
      3. Chama booking_engine.update() com a ação
      4. Sincroniza o estado da BotSession com o novo estado da BookingSession
      5. Envia as mensagens via WhatsAppResponseFormatter
    """
    from app.infrastructure.db.models.booking_session import BookingSession as _BookingSession
    from uuid import UUID as _UUID
    from app.modules.booking.engine import booking_engine
    from app.modules.booking.actions import BookingAction, SessionExpiredError, InvalidActionError
    from app.modules.whatsapp.input_parser import whatsapp_input_parser
    from app.modules.whatsapp.response_formatter import whatsapp_response_formatter

    ctx                = session.context or {}
    booking_session_id = ctx.get("booking_session_id")
    state              = session.state

    # ── Guard: sem booking_session_id → contexto corrompido ──────────────────
    if not booking_session_id:
        logger.warning(
            "BOOKING_STATE sem booking_session_id. state=%s whatsapp_id=%s", state, whatsapp_id
        )
        reset_session(session, keep_customer=True)
        ctx2 = session.context or {}
        h_inicio.show_menu_principal(
            session, ctx2, instance, whatsapp_id,
            ctx2.get("company_name", "Barbearia"), ctx2.get("customer_name"),
        )
        return

    # ── Carregar BookingSession ───────────────────────────────────────────────
    try:
        bs_id = _UUID(booking_session_id)
    except (ValueError, TypeError):
        logger.error("booking_session_id inválido=%s", booking_session_id)
        reset_session(session, keep_customer=True)
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        return

    booking_session = (
        db.query(_BookingSession)
        .filter(
            _BookingSession.id == bs_id,
            _BookingSession.company_id == company_id,
        )
        .first()
    )

    if not booking_session:
        logger.warning("BookingSession não encontrada id=%s, reiniciando fluxo", booking_session_id)
        reset_session(session, keep_customer=True)
        ctx2 = session.context or {}
        h_inicio.show_menu_principal(
            session, ctx2, instance, whatsapp_id,
            ctx2.get("company_name", "Barbearia"), ctx2.get("customer_name"),
        )
        return

    # ── Parsear input ─────────────────────────────────────────────────────────
    parse_result = whatsapp_input_parser.parse(
        user_input, state, booking_session.context or {}, company_timezone
    )

    if parse_result is None:
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return

    action, payload = parse_result

    # ── RESET → volta ao menu principal sem chamar o engine ──────────────────
    if action == BookingAction.RESET:
        reset_session(session, keep_customer=True)
        ctx2 = session.context or {}
        h_inicio.show_menu_principal(
            session, ctx2, instance, whatsapp_id,
            ctx2.get("company_name", "Barbearia"), ctx2.get("customer_name"),
        )
        return

    # ── Aplicar ação no BookingEngine ────────────────────────────────────────
    try:
        result = booking_engine.update(db, booking_session, action, payload)
    except SessionExpiredError:
        reset_session(session, keep_customer=True)
        ctx2 = session.context or {}
        sender.send_text(instance, whatsapp_id, "⏰ Sua sessão expirou. Começando de novo 😊")
        h_inicio.show_menu_principal(
            session, ctx2, instance, whatsapp_id,
            ctx2.get("company_name", "Barbearia"), ctx2.get("customer_name"),
        )
        return
    except InvalidActionError as e:
        logger.warning("InvalidActionError state=%s action=%s: %s", state, action, e)
        sender.send_text(instance, whatsapp_id, messages.ESCOLHA_OPCAO_OPS)
        return
    except Exception:
        logger.exception("booking_engine.update error state=%s whatsapp_id=%s", state, whatsapp_id)
        sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
        return

    # ── Auto-bypass AWAITING_CUSTOMER (WhatsApp: cliente já identificado) ────
    # O engine retorna AWAITING_CUSTOMER para pedir nome/telefone ao canal web.
    # No WhatsApp o cliente é identificado desde o estado INICIO, portanto
    # avançamos automaticamente para AWAITING_CONFIRMATION (ou voltamos a
    # AWAITING_TIME se o usuário escolheu "Alterar horário").
    if result.next_state == "AWAITING_CUSTOMER":
        bot_ctx     = session.context or {}
        customer_id = bot_ctx.get("customer_id")

        if not customer_id:
            logger.error(
                "Auto-bypass AWAITING_CUSTOMER: customer_id ausente. whatsapp_id=%s", whatsapp_id
            )
            sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
            return

        bypass_action  = BookingAction.BACK if action == BookingAction.BACK else BookingAction.SET_CUSTOMER
        bypass_payload = {} if action == BookingAction.BACK else {"customer_id": customer_id}

        try:
            result = booking_engine.update(db, booking_session, bypass_action, bypass_payload)
        except Exception:
            logger.exception(
                "Auto-bypass SET_CUSTOMER falhou. whatsapp_id=%s action=%s",
                whatsapp_id, bypass_action,
            )
            sender.send_text(instance, whatsapp_id, messages.ERRO_GENERICO)
            return

    # ── Sincronizar estado da BotSession com o novo estado da BookingSession ──
    new_state = result.next_state

    if new_state in ("CONFIRMED", "CANCELLED"):
        # Fluxo concluído → resetar mantendo cliente identificado para próxima conversa
        reset_session(session, keep_customer=True)
    elif new_state in BOOKING_STATES:
        session.state = new_state
    else:
        # Estado transitório (CONFIRMING) ou inesperado → manter estado atual
        # O engine pode ter voltado a um BOOKING_STATE via BACK/RESET
        if booking_session.state in BOOKING_STATES:
            session.state = booking_session.state
        else:
            logger.warning("Estado inesperado após update new_state=%s bs_state=%s",
                           new_state, booking_session.state)

    # ── Enviar mensagens ao usuário ───────────────────────────────────────────
    whatsapp_response_formatter.format_and_send(
        result, instance, whatsapp_id,
        booking_session.context or {}, company_timezone,
    )


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
            logger.debug("handle_inbound: messages array vazio, ignorando. instance=%s", instance_name)
            return
        data = messages_list[0]

    key = data.get("key", {})
    if key.get("fromMe"):
        logger.debug("handle_inbound: fromMe=True, ignorando. instance=%s", instance_name)
        return

    message_id = key.get("id", "")

    # LID addressing mode (WhatsApp novo formato)
    addressing_mode = key.get("addressingMode", "")
    remote_jid_alt  = key.get("remoteJidAlt", "")
    raw_jid         = key.get("remoteJid", "")
    remote_jid = remote_jid_alt if (addressing_mode == "lid" and remote_jid_alt) else raw_jid

    if not remote_jid:
        logger.warning("handle_inbound: sem remoteJid. instance=%s data_keys=%s",
                       instance_name, list(data.keys()))
        return
    if remote_jid.endswith("@g.us"):
        logger.debug("handle_inbound: grupo ignorado. jid=%s", remote_jid)
        return

    # Usa o JID completo como identificador — _normalize_number retorna como está
    # quando já contém "@", garantindo entrega correta tanto para @s.whatsapp.net
    # quanto para @lid (LID addressing mode do WhatsApp novo).
    whatsapp_id = remote_jid   # ex: "5511999999999@s.whatsapp.net" ou "97148318265437@lid"

    # Resolve empresa pelo instance_name
    conn = db.query(WhatsAppConnection).filter(
        WhatsAppConnection.instance_name == instance_name
    ).first()
    if not conn:
        logger.warning("handle_inbound: instance_name=%s não encontrado no DB", instance_name)
        return

    company_id = conn.company_id

    # Verifica se bot está ativo
    company_settings = db.query(CompanySettings).filter(
        CompanySettings.company_id == company_id
    ).first()
    if not company_settings:
        logger.warning("handle_inbound: company_settings não encontrado. company_id=%s", company_id)
        return
    if not company_settings.bot_enabled:
        logger.info("handle_inbound: bot desativado. company_id=%s", company_id)
        return

    company          = db.query(Company).filter(Company.id == company_id).first()
    company_name     = company.name if company else "Barbearia"
    company_timezone = (company.timezone if company else None) or "America/Sao_Paulo"
    user_input       = extract_user_text(data)

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

    # Injeta timezone da empresa no contexto — handlers usam para exibir horários locais
    ctx = session.context or {}
    if ctx.get("company_timezone") != company_timezone:
        ctx = dict(ctx)
        ctx["company_timezone"] = company_timezone
        session.context = ctx

    state = session.state
    logger.info("dispatcher: state=%s whatsapp_id=%s input=%r", state, whatsapp_id, user_input[:60])

    # ── Comandos universais (exceto AGUARDANDO_NOME, CONFIRMAR_NOME e HUMANO) ──
    if state not in (STATE_AGUARDANDO_NOME, STATE_CONFIRMAR_NOME, STATE_HUMANO):
        cmd = is_universal_command(user_input)
        if cmd == "menu":
            reset_session(session)
            ctx = session.context or {}
            h_inicio.show_menu_principal(session, ctx, instance_name, whatsapp_id,
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
            sender.send_text(instance_name, whatsapp_id, messages.HUMANO_CHAMADO)
            save_session(db, session)
            return

    # ── Dispatcher principal ──────────────────────────────────────────────────
    try:
        if state == STATE_INICIO:
            h_inicio.handle(
                db, session, company_id, whatsapp_id, instance_name,
                company_name, user_input,
                start_escolhendo_servico=_start_escolhendo_servico,
                handle_ver_agendamentos=_handle_ver_agendamentos,
                resolve_input=resolve_input,
            )

        elif state == STATE_AGUARDANDO_NOME:
            h_nome.handle_aguardando_nome(
                db, session, company_id, whatsapp_id, instance_name, user_input,
            )

        elif state == STATE_CONFIRMAR_NOME:
            h_nome.handle_confirmando_nome(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                start_escolhendo_servico=_start_escolhendo_servico,
            )

        elif state == STATE_OFERTA_RECORRENTE:
            h_oferta.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_escolhendo_servico=_start_escolhendo_servico,
                start_escolhendo_horario=_start_escolhendo_horario,
                send_confirmacao_resumo=h_confirmando.send_resumo,
                send_escolher_data=_send_escolher_data,
            )

        elif state == STATE_MENU_PRINCIPAL:
            h_menu.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                start_escolhendo_servico=_start_escolhendo_servico,
                handle_ver_agendamentos=_handle_ver_agendamentos,
            )

        elif state == STATE_ESCOLHENDO_SERVICO:
            h_servico.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_escolhendo_profissional=_start_escolhendo_profissional,
            )

        elif state == STATE_ESCOLHENDO_PROFISSIONAL:
            h_profissional.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                send_escolher_data=_send_escolher_data,
            )

        elif state == STATE_ESCOLHENDO_DATA:
            h_data.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_escolhendo_turno=_start_escolhendo_turno,
            )

        elif state == STATE_ESCOLHENDO_TURNO:
            h_turno.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_escolhendo_horario=_start_escolhendo_horario,
            )

        elif state == STATE_ESCOLHENDO_HORARIO:
            h_horario.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                send_escolher_data=_send_escolher_data,
                send_confirmacao_resumo=h_confirmando.send_resumo,
            )

        elif state == STATE_CONFIRMANDO:
            h_confirmando.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_escolhendo_horario=_start_escolhendo_horario,
            )

        elif state == STATE_VER_AGENDAMENTOS:
            h_ver.handle_input(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_gerenciando_agendamento=_start_gerenciando_agendamento,
                show_menu_principal=h_inicio.show_menu_principal,
            )

        elif state == STATE_GERENCIANDO_AGENDAMENTO:
            h_gerenciando.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                handle_ver_agendamentos=_handle_ver_agendamentos,
                start_cancelando=_start_cancelando,
                start_escolhendo_horario=_start_escolhendo_horario,
                start_escolhendo_servico=_start_escolhendo_servico,
            )

        elif state == STATE_CANCELANDO:
            h_cancelando.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                start_gerenciando_agendamento=_start_gerenciando_agendamento,
            )

        elif state == STATE_REAGENDANDO:
            h_reagendando.handle(
                db, session, company_id, whatsapp_id, instance_name, user_input,
                resolve_input=resolve_input,
                send_escolher_data=_send_escolher_data,
                start_escolhendo_horario=_start_escolhendo_horario,
            )

        elif state in BOOKING_STATES:
            # Fluxo unificado via BookingEngine FSM
            _handle_booking_state(
                db, session, company_id, instance_name, whatsapp_id,
                user_input, company_timezone,
            )

        elif state == STATE_HUMANO:
            pass  # Silêncio — atendente assume a conversa

        else:
            logger.warning("estado desconhecido state=%s, resetando sessão", state)
            reset_session(session, keep_customer=False)

    except Exception:
        logger.exception("bot error state=%s whatsapp_id=%s", state, whatsapp_id)
        sender.send_text(instance_name, whatsapp_id, messages.ERRO_GENERICO)

    try:
        save_session(db, session)
    except Exception:
        logger.exception("save_session error state=%s whatsapp_id=%s", state, whatsapp_id)