"""
Políticas de negócio para agendamentos.

Funções puras (sem acesso a DB) que podem ser testadas isoladamente.
A camada de serviço chama estas funções antes de executar operações críticas.

Exceção centralizada:
    PolicyViolationError — levantada quando uma regra de negócio é violada.
    O router de appointments captura e retorna HTTP 422.

Códigos de violação (code):
    CANCELLATION_TOO_LATE   — tentativa de cancelamento dentro do prazo mínimo
    RESCHEDULE_TOO_LATE     — tentativa de reagendamento dentro do prazo mínimo
    APPOINTMENT_ALREADY_PAST — agendamento já passou, operação inválida
"""
from datetime import datetime, timezone, timedelta


# ─────────────────────────────────────────────────────────────────────────────
# Códigos de violação de política
# ─────────────────────────────────────────────────────────────────────────────

CANCELLATION_TOO_LATE    = "CANCELLATION_TOO_LATE"
RESCHEDULE_TOO_LATE      = "RESCHEDULE_TOO_LATE"
APPOINTMENT_ALREADY_PAST = "APPOINTMENT_ALREADY_PAST"


# ─────────────────────────────────────────────────────────────────────────────
# Exceção
# ─────────────────────────────────────────────────────────────────────────────

class PolicyViolationError(Exception):
    """
    Levantada quando uma operação viola uma política de negócio.

    Atributos:
        code   — constante de string identificando a violação (ex: CANCELLATION_TOO_LATE)
        detail — mensagem legível por humanos
    """
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail


# ─────────────────────────────────────────────────────────────────────────────
# Funções puras de verificação de política
# ─────────────────────────────────────────────────────────────────────────────

def check_cancellation_policy(
    start_at: datetime,
    now: datetime,
    min_hours: int,
) -> tuple[bool, str]:
    """
    Verifica se um agendamento pode ser cancelado com base no prazo mínimo.

    Returns:
        (True, "")                    se o cancelamento é permitido
        (False, motivo_legivel)       se o cancelamento é negado
    """
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if now >= start_at:
        return False, "O agendamento já passou. Não é possível cancelar."

    remaining = start_at - now
    if remaining < timedelta(hours=min_hours):
        hours_left = int(remaining.total_seconds() // 3600)
        return (
            False,
            f"O prazo para cancelamento encerrou. "
            f"É necessário cancelar com pelo menos {min_hours}h de antecedência "
            f"(faltam apenas {hours_left}h).",
        )

    return True, ""


def check_reschedule_policy(
    start_at: datetime,
    now: datetime,
    min_hours: int,
) -> tuple[bool, str]:
    """
    Verifica se um agendamento pode ser reagendado com base no prazo mínimo.

    Returns:
        (True, "")                    se o reagendamento é permitido
        (False, motivo_legivel)       se o reagendamento é negado
    """
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    if now >= start_at:
        return False, "O agendamento já passou. Não é possível reagendar."

    remaining = start_at - now
    if remaining < timedelta(hours=min_hours):
        hours_left = int(remaining.total_seconds() // 3600)
        return (
            False,
            f"O prazo para reagendamento encerrou. "
            f"É necessário reagendar com pelo menos {min_hours}h de antecedência "
            f"(faltam apenas {hours_left}h).",
        )

    return True, ""
