"""
Bot de agendamento via WhatsApp — máquina de estados.

Fluxo:
  INICIO → [AGUARDANDO_NOME] → [CONFIRMAR_NOME]
         → [OFERTA_RECORRENTE] | MENU_PRINCIPAL
         → ESCOLHENDO_SERVICO → ESCOLHENDO_PROFISSIONAL
         → ESCOLHENDO_DATA → ESCOLHENDO_HORARIO
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
STATE_ESCOLHENDO_HORARIO      = "ESCOLHENDO_HORARIO"
STATE_ESCOLHENDO_DATA         = "ESCOLHENDO_DATA"
STATE_CONFIRMANDO             = "CONFIRMANDO"
STATE_VER_AGENDAMENTOS        = "VER_AGENDAMENTOS"
STATE_GERENCIANDO_AGENDAMENTO = "GERENCIANDO_AGENDAMENTO"
STATE_CANCELANDO              = "CANCELANDO"
STATE_REAGENDANDO             = "REAGENDANDO"
STATE_HUMANO                  = "HUMANO"


# ─── Wrappers locais (evitam repetir db/session nos handlers) ─────────────────
# Cada _start_* é uma função local que fecha sobre db/session/company_id,
# permitindo que os handlers a recebam como callable sem conhecer bot_service.

def _mk_start_servico(db, session, company_id):
    def _f(db_, sess_, cid_, inst_, wid_):
        h_servico.start(db_, sess_, cid_, inst_, wid_)
    return _f


def _start_escolhendo_servico(db: Session, session: BotSession, company_id: UUID,
                               instance: str, whatsapp_id: str) -> None:
    h_servico.start(db, session, company_id, instance, whatsapp_id)


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

    company      = db.query(Company).filter(Company.id == company_id).first()
    company_name = company.name if company else "Barbearia"
    user_input   = extract_user_text(data)

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