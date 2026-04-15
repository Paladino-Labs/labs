"""
Exceções do domínio de agendamento, agnósticas de canal.

SlotUnavailableError  → horário já ocupado ou fora da janela de trabalho (HTTP 409)
BookingNotFoundError  → agendamento não encontrado (HTTP 404)
PolicyViolationError  → regra de negócio violada, re-exportada de polices.py

Esses tipos são capturados pelos handlers do bot e pelos routers HTTP.
Nunca chegam ao usuário como traceback — são convertidos em mensagem amigável.
"""
from app.modules.appointments.polices import PolicyViolationError  # noqa: F401 (re-export)


class SlotUnavailableError(Exception):
    """Slot solicitado não está disponível no momento da confirmação."""

    def __init__(self, detail: str = "Horário indisponível") -> None:
        super().__init__(detail)
        self.detail = detail


class BookingNotFoundError(Exception):
    """Agendamento não encontrado para a empresa."""

    def __init__(self, appointment_id=None) -> None:
        msg = f"Agendamento {appointment_id} não encontrado" if appointment_id else "Agendamento não encontrado"
        super().__init__(msg)
        self.detail = msg
