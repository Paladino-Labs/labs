"""
Token de gestão de agendamento (Sprint B).

O cliente recebe no WhatsApp um link único para remarcar/cancelar sem login:
    {FRONTEND_BASE_URL}/manage/{token}

Contrato de segurança:
  - Token cru = UUID4 — enviado apenas no link; NUNCA armazenado.
  - No banco fica somente o SHA-256 (appointments.manage_token_hash).
  - Expira em start_at (após o início do atendimento o link morre).
  - Invalidado ao atingir estado terminal (COMPLETED/CANCELLED/NO_SHOW)
    — ver transitions.py.
"""
import hashlib
import uuid
from typing import TYPE_CHECKING

from app.core.config import settings

if TYPE_CHECKING:
    from app.infrastructure.db.models import Appointment


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def issue_manage_token(appointment: "Appointment") -> str:
    """
    Gera um token novo para o appointment (invalida o anterior, se houver).
    Persiste apenas o hash; retorna o token cru para inclusão no link.
    Não faz commit — o chamador controla a transação.
    """
    raw = str(uuid.uuid4())
    appointment.manage_token_hash = hash_token(raw)
    appointment.manage_token_expires_at = appointment.start_at
    return raw


def invalidate_manage_token(appointment: "Appointment") -> None:
    appointment.manage_token_hash = None
    appointment.manage_token_expires_at = None


def build_manage_url(raw_token: str) -> str:
    base = (settings.FRONTEND_BASE_URL or settings.FRONTEND_URL).rstrip("/")
    return f"{base}/manage/{raw_token}"
