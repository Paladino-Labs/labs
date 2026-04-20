"""
Schemas HTTP do router público de booking.

Separados dos dataclasses internos de booking/schemas.py — estes são os
contratos de entrada e saída da API REST, com validação Pydantic e
serialização automática pelo FastAPI.

Convenção de nomes:
  *Request  — body de entrada (POST/PATCH)
  *Response — body de saída

Seção BookingSession FSM (Fase 2):
  StartSessionRequest/Response  — POST /booking/{slug}/start
  UpdateSessionRequest/Response — POST /booking/{slug}/update
  SessionStateResponse          — GET  /booking/{slug}/session/{token}

Convenção de datas na resposta:
  start_at / end_at  → ISO 8601 UTC (para cálculos no cliente)
  start_display      → HH:MM no timezone da empresa (para exibição direta)
  date_label         → texto legível já formatado pelo engine (ex: "Hoje (20/04)")
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Any, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator


# ─── Saída: /info ─────────────────────────────────────────────────────────────

class CompanyInfoResponse(BaseModel):
    company_name: str
    active: bool
    online_booking_enabled: bool
    services_count: int
    booking_url: str        # URL pública compartilhável — ex: "https://app.meupaladino.com.br/paladino-labs"


# ─── Saída: /services ─────────────────────────────────────────────────────────

class ServiceOptionResponse(BaseModel):
    id: UUID
    name: str
    price: Decimal
    duration_minutes: int
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /professionals ────────────────────────────────────────────────────

class ProfessionalOptionResponse(BaseModel):
    id: Optional[UUID]      # None = "Qualquer disponível"
    name: str
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /dates ────────────────────────────────────────────────────────────

class DateOptionResponse(BaseModel):
    date: date
    label: str
    has_availability: bool
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: /slots ────────────────────────────────────────────────────────────

class SlotOptionResponse(BaseModel):
    start_at: datetime
    end_at: datetime
    professional_id: UUID
    professional_name: str
    row_key: str

    model_config = ConfigDict(from_attributes=True)


# ─── Entrada: POST /confirm ───────────────────────────────────────────────────

class ConfirmBookingRequest(BaseModel):
    service_id: UUID
    professional_id: UUID           # deve ser UUID concreto; "any" resolvido pelo frontend
    start_at: datetime
    customer_phone: str             # usado para identificar/criar o cliente
    customer_name: str
    idempotency_key: str


# ─── Saída: POST /confirm ─────────────────────────────────────────────────────

class BookingResultResponse(BaseModel):
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal

    model_config = ConfigDict(from_attributes=True)


# ─── Saída: GET /appointments ─────────────────────────────────────────────────

class AppointmentSummaryResponse(BaseModel):
    id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    status: str

    model_config = ConfigDict(from_attributes=True)


# ─── Entrada: PATCH /appointments/{id}/cancel ────────────────────────────────

class CancelBookingRequest(BaseModel):
    reason: Optional[str] = None
    phone: str                      # identifica o cliente para autorização


# ─── Saída: PATCH /appointments/{id}/cancel ──────────────────────────────────

class CancelResultResponse(BaseModel):
    success: bool
    message: str


# ═══════════════════════════════════════════════════════════════════════════════
# BookingSession FSM — Fase 2
# Endpoint único POST /booking/{slug}/update
# ═══════════════════════════════════════════════════════════════════════════════

# ─── Opções serializadas para resposta HTTP ───────────────────────────────────

class ServiceOptionHTTP(BaseModel):
    """Serviço disponível para seleção."""
    id: UUID
    name: str
    price: str              # string para evitar problema de serialização de Decimal no JS
    duration_minutes: int
    row_key: str


class ProfessionalOptionHTTP(BaseModel):
    """Profissional disponível (id=None = 'Qualquer disponível')."""
    id: Optional[UUID]
    name: str
    row_key: str


class DateOptionHTTP(BaseModel):
    """Data com indicação de disponibilidade."""
    date: date
    label: str              # ex: "Hoje (20/04)" — já no tz da empresa
    has_availability: bool
    row_key: str


class SlotOptionHTTP(BaseModel):
    """
    Horário disponível.

    start_at       → UTC ISO 8601 — para cálculos no cliente ("falta X horas")
    start_display  → HH:MM no timezone da empresa — para exibição direta ao usuário
    """
    start_at: datetime          # UTC
    end_at: datetime            # UTC
    start_display: str          # "14:30" no timezone da empresa
    professional_id: UUID
    professional_name: str
    row_key: str


# ─── Confirmação serializada ──────────────────────────────────────────────────

class ConfirmationHTTP(BaseModel):
    """Dados do agendamento criado — retornado quando state='CONFIRMED'."""
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime          # UTC
    start_display: str          # "14:30" no timezone da empresa
    end_at: datetime            # UTC
    total_amount: str           # string para evitar problema de Decimal no JS


class CancelConfirmationHTTP(BaseModel):
    """Resultado de cancelamento — retornado quando state='CANCELLED'."""
    success: bool
    message: str


# ─── POST /booking/{slug}/start ──────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    """
    Cria uma nova BookingSession.
    customer_phone é opcional: se fornecido e o cliente já existir,
    pula o passo SET_CUSTOMER e inicia direto em AWAITING_SERVICE.
    """
    customer_phone: Optional[str] = None
    customer_name: Optional[str] = None


class StartSessionResponse(BaseModel):
    """
    Resposta de POST /booking/{slug}/start.

    session_id  → usar em todos os POSTs subsequentes de /update
    token       → persistir no frontend para retomada via URL (?t={token})
    state       → estado inicial (sempre "IDLE" ou "AWAITING_SERVICE" se cliente pré-identificado)
    options     → lista de serviços quando state="AWAITING_SERVICE" (cliente já identificado no /start)
                  lista vazia quando state="IDLE" (frontend exibirá formulário de identificação)
    expires_at  → UTC; frontend pode usar para countdown de expiração
    """
    session_id: UUID
    token: str
    state: str
    options: list[Any] = []     # ServiceOptionHTTP[] quando state=AWAITING_SERVICE
    expires_at: datetime        # UTC
    company_timezone: str       # ex: "America/Sao_Paulo" — para conversões no frontend


# ─── POST /booking/{slug}/update ─────────────────────────────────────────────

class UpdateSessionRequest(BaseModel):
    """
    Aplica uma ação à sessão e avança o FSM.

    session_id  → UUID retornado por /start
    action      → string da BookingAction (ex: "SELECT_SERVICE")
    payload     → dados da ação (depende da action):
                  SET_CUSTOMER:        {name, phone}
                  SELECT_SERVICE:      {service_id} ou {row_key}
                  SELECT_PROFESSIONAL: {professional_id} ou {row_key: "prof_any"}
                  SELECT_DATE:         {date: "YYYY-MM-DD"} ou {row_key}
                  SELECT_TIME:         {start_at: ISO} ou {row_key}
                  CONFIRM:             {}
                  BACK:                {}
                  RESET:               {}
                  CANCEL_START:        {appointment_id}
                  CONFIRM_CANCEL:      {}
    """
    session_id: UUID
    action: str
    payload: dict = {}


class UpdateSessionResponse(BaseModel):
    """
    Resposta de POST /booking/{slug}/update.

    state           → novo estado da sessão após a ação
    options         → lista de opções para o próximo passo
                      (tipo varia por estado: ServiceOptionHTTP | ProfessionalOptionHTTP |
                       DateOptionHTTP | SlotOptionHTTP)
    confirmation    → preenchido quando state='CONFIRMED'
    cancel_result   → preenchido quando state='CANCELLED'
    error           → código de erro se ação falhou mas sessão sobreviveu
                      ex: "SLOT_UNAVAILABLE" → state voltou para AWAITING_TIME com novos slots
    idempotent      → True se CONFIRM foi replay de agendamento já existente
    expires_at      → TTL atualizado da sessão (UTC)
    """
    state: str
    options: list[Any]          # list[ServiceOptionHTTP | ProfessionalOptionHTTP | ...]
    confirmation: Optional[ConfirmationHTTP] = None
    cancel_result: Optional[CancelConfirmationHTTP] = None
    error: Optional[str] = None
    idempotent: bool = False
    expires_at: datetime        # UTC — refreshado a cada ação bem-sucedida


# ─── GET /booking/{slug}/session/{token} ─────────────────────────────────────

class SessionStateResponse(BaseModel):
    """
    Resposta de GET /booking/{slug}/session/{token} (retomada de sessão).

    Retorna o estado atual + opções re-listadas do banco (slots podem ter mudado).
    O frontend hidrata o wizard sem precisar recomeçar do início.
    """
    session_id: UUID
    token: str
    state: str
    options: list[Any]
    confirmation: Optional[ConfirmationHTTP] = None
    expires_at: datetime        # UTC
    company_timezone: str