"""
Ações e exceções do BookingSession unificado.

BookingAction  — enum de todas as ações que podem ser aplicadas a uma sessão.
SessionExpiredError  — sessão TTL esgotado; o caller deve criar nova sessão.
InvalidActionError   — ação incompatível com o estado atual da sessão.
"""
from enum import Enum
from uuid import UUID


class BookingAction(str, Enum):
    """
    Ações que o booking_engine.update() reconhece.

    Cada ação é válida apenas em determinados estados (ver _VALID_TRANSITIONS
    em BookingEngine). Tentar uma ação fora de contexto levanta InvalidActionError.
    """
    # ─── Fluxo principal ─────────────────────────────────────────────────────
    SET_CUSTOMER        = "SET_CUSTOMER"        # payload: {name, phone, email?}
    SELECT_SERVICE      = "SELECT_SERVICE"      # payload: {service_id} | {row_key}
    SELECT_PROFESSIONAL = "SELECT_PROFESSIONAL" # payload: {professional_id} | {row_key: "prof_any"}
    SELECT_DATE         = "SELECT_DATE"         # payload: {date: "YYYY-MM-DD"} | {row_key}
    SELECT_TIME         = "SELECT_TIME"         # payload: {start_at: ISO} | {row_key}
    CONFIRM             = "CONFIRM"             # payload: {} — cria o agendamento

    # ─── Turno ───────────────────────────────────────────────────────────────
    SELECT_SHIFT        = "SELECT_SHIFT"        # payload: {shift: "manha"|"tarde"|"noite"}

    # ─── Navegação ────────────────────────────────────────────────────────────
    BACK                = "BACK"                # payload: {} — volta um passo
    RESET               = "RESET"              # payload: {} — volta ao início (mantém customer)
    NAVIGATE_DATES      = "NAVIGATE_DATES"      # payload: {offset_days: int} — troca janela de datas

    # ─── Gestão de agendamentos existentes ───────────────────────────────────
    RESCHEDULE_START    = "RESCHEDULE_START"    # payload: {appointment_id}
    CANCEL_START        = "CANCEL_START"        # payload: {appointment_id}
    CONFIRM_CANCEL      = "CONFIRM_CANCEL"      # payload: {} — confirma o cancelamento


class SessionExpiredError(Exception):
    """
    Sessão expirada (expires_at < now).
    O caller (endpoint HTTP ou handler do bot) deve criar nova sessão e
    retornar erro adequado ao canal (HTTP 410, mensagem de texto no WhatsApp).
    """
    def __init__(self, session_id=None) -> None:
        msg = f"Sessão {session_id} expirada" if session_id else "Sessão expirada"
        super().__init__(msg)
        self.session_id = session_id


class InvalidActionError(Exception):
    """
    Ação solicitada não é válida para o estado atual da sessão.
    HTTP 422 para o endpoint; fallback de texto para o bot.
    """
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.detail = message
