"""
Estruturas de dados do BookingEngine.

Estas são as fronteiras de entrada e saída da camada de orquestração —
agnósticas de canal (HTTP, WhatsApp, qualquer outro).
"""
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional
from uuid import UUID


@dataclass
class ServiceOption:
    id: UUID
    name: str
    price: Decimal
    duration_minutes: int
    row_key: str            # "serv_1", "serv_2" — índice estável para mapeamento de input


@dataclass
class ProfessionalOption:
    id: Optional[UUID]      # None para "Qualquer disponível"
    name: str
    row_key: str            # "prof_1", "prof_2", "prof_any"


@dataclass
class DateOption:
    date: date
    label: str              # "Hoje (14/04)", "Amanhã (15/04)", "Quarta (16/04)"
    has_availability: bool
    row_key: str            # "dia_1", "dia_2"


@dataclass
class SlotOption:
    start_at: datetime
    end_at: datetime
    professional_id: UUID
    professional_name: str
    row_key: str            # "slot_1", "slot_2"


@dataclass
class BookingIntent:
    company_id: UUID
    customer_id: UUID
    professional_id: UUID       # deve estar resolvido (nunca None aqui)
    service_id: UUID
    start_at: datetime
    idempotency_key: str


@dataclass
class BookingResult:
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal


@dataclass
class AppointmentSummary:
    id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    status: str


@dataclass
class PredictiveOfferResult:
    service_id: UUID
    service_name: str
    professional_id: UUID
    professional_name: str
    next_slot: datetime
    expires_at: datetime


@dataclass
class CancelResult:
    success: bool
    message: str


@dataclass
class RescheduleResult:
    success: bool
    new_start_at: datetime
    message: str
