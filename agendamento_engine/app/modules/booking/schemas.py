"""
Data structures returned by BookingEngine and predictor.

All structs are plain dataclasses — no validation, no serialisation logic.
Callers (bot, HTTP, admin) are responsible for rendering/formatting.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID


@dataclass
class ServiceOption:
    """One item in the services menu.  row_key uses prefix 'serv_' + index."""
    row_key: str           # "serv_0", "serv_1", ...
    id: UUID
    name: str
    price: Decimal
    duration_minutes: int


@dataclass
class ProfessionalOption:
    """One item in the professionals menu.  row_key uses prefix 'prof_' + index."""
    row_key: str           # "prof_0", "prof_1", ...
    id: UUID
    name: str


@dataclass
class DateOption:
    """One available date.  row_key uses prefix 'date_' + index."""
    row_key: str           # "date_0", "date_1", ...
    date: date


@dataclass
class SlotOption:
    """One available time slot.  row_key uses prefix 'slot_' + index."""
    row_key: str           # "slot_0", "slot_1", ...
    start_at: datetime
    end_at: datetime


@dataclass
class BookingIntent:
    """What the caller wants to book.  Passed to BookingEngine.book()."""
    customer_id: UUID
    service_id: UUID
    professional_id: UUID
    start_at: datetime
    idempotency_key: str


@dataclass
class BookingResult:
    """Result of a successful booking, or one item from get_active_bookings()."""
    appointment_id: UUID
    service_name: str
    professional_name: str
    start_at: datetime
    end_at: datetime
    total_amount: Decimal


@dataclass
class PredictiveOfferResult:
    """
    Predictive suggestion for a returning customer.
    Contains no formatted text — callers render labels themselves.
    expires_at is the TTL boundary; callers must check before confirming.
    """
    service_id: UUID
    service_name: str
    professional_id: UUID
    professional_name: str
    slot_start_at: datetime
    slot_end_at: datetime
    expires_at: datetime


@dataclass
class CancelResult:
    """Result of a successful cancellation."""
    appointment_id: UUID
    cancelled_at: datetime


@dataclass
class RescheduleResult:
    """Result of a successful reschedule."""
    appointment_id: UUID
    new_start_at: datetime
    new_end_at: datetime
