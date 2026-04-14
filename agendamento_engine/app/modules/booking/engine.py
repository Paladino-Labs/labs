"""
BookingEngine — thin orchestration layer over existing domain services.

Responsibilities:
  - Query services, professionals, dates, and slots in a standardised form.
  - Create, cancel, and reschedule appointments via appointments.service.
  - Return typed dataclasses; no channel-specific logic.

What this module does NOT do:
  - Recalculate availability (delegated to availability.service).
  - Validate slot rules (delegated to appointments.service).
  - Contain WhatsApp, HTTP, or Evolution API code.

All methods are stateless.  db session and company_id are explicit parameters
on every call so the engine remains independent of request context.
"""
import logging
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.appointments import service as appointment_svc
from app.modules.appointments.schemas import (
    AppointmentCreate,
    RescheduleRequest,
    ServiceRequest,
)
from app.modules.availability import service as availability_svc
from app.modules.professionals import service as professional_svc
from app.modules.services import service as service_svc
from app.modules.booking.exceptions import BookingNotFoundError, SlotUnavailableError
from app.modules.booking.schemas import (
    BookingIntent,
    BookingResult,
    CancelResult,
    DateOption,
    ProfessionalOption,
    RescheduleResult,
    ServiceOption,
    SlotOption,
)

logger = logging.getLogger(__name__)


def _http_exc_to_domain(exc: Exception) -> Exception:
    """
    Translate an HTTPException from the service layer into a domain exception.

    The existing services use FastAPI's HTTPException as their error mechanism.
    This helper converts status codes to domain exceptions without requiring
    the engine to import from fastapi.
    """
    status = getattr(exc, "status_code", None)
    detail = str(getattr(exc, "detail", exc))
    if status == 404:
        return BookingNotFoundError(detail)
    return SlotUnavailableError(detail)


class BookingEngine:
    """Thin orchestrator for the booking flow."""

    # ------------------------------------------------------------------
    # Options queries
    # ------------------------------------------------------------------

    @staticmethod
    def list_services(db: Session, company_id: UUID) -> list[ServiceOption]:
        """Return active services sorted by name."""
        services = service_svc.list_services(db, company_id, active_only=True)
        return [
            ServiceOption(
                row_key=f"serv_{i}",
                id=s.id,
                name=s.name,
                price=s.price,
                duration_minutes=s.duration,
            )
            for i, s in enumerate(sorted(services, key=lambda s: s.name))
        ]

    @staticmethod
    def list_professionals(
        db: Session, company_id: UUID, service_id: UUID
    ) -> list[ProfessionalOption]:
        """Return professionals who offer the given service, sorted by name."""
        professionals = professional_svc.list_by_service(db, company_id, service_id)
        return [
            ProfessionalOption(row_key=f"prof_{i}", id=p.id, name=p.name)
            for i, p in enumerate(sorted(professionals, key=lambda p: p.name))
        ]

    @staticmethod
    def list_dates(
        db: Session,
        company_id: UUID,
        professional_id: UUID,
        service_id: UUID,
        days: int = 30,
    ) -> list[DateOption]:
        """
        Return distinct dates that have at least one available slot, sorted ascending.

        Fetches up to 200 slots across the requested horizon in a single query
        to avoid per-date round-trips.
        """
        slots = availability_svc.get_next_available_slots(
            db, company_id, professional_id, service_id, days=days, limit=200
        )
        seen: set[date] = set()
        result: list[DateOption] = []
        for slot in sorted(slots, key=lambda s: s.start_at):
            d = slot.start_at.date()
            if d not in seen:
                seen.add(d)
                result.append(DateOption(row_key=f"date_{len(result)}", date=d))
        return result

    @staticmethod
    def list_slots(
        db: Session,
        company_id: UUID,
        professional_id: UUID,
        service_id: UUID,
        target_date: date,
    ) -> list[SlotOption]:
        """Return available slots for a specific date, sorted by start time."""
        slots = availability_svc.get_available_slots(
            db, company_id, professional_id, service_id, target_date
        )
        return [
            SlotOption(row_key=f"slot_{i}", start_at=s.start_at, end_at=s.end_at)
            for i, s in enumerate(sorted(slots, key=lambda s: s.start_at))
        ]

    # ------------------------------------------------------------------
    # Booking mutations
    # ------------------------------------------------------------------

    @staticmethod
    def book(db: Session, company_id: UUID, intent: BookingIntent) -> BookingResult:
        """
        Create an appointment from a BookingIntent.

        Raises:
            SlotUnavailableError: slot is taken, capacity exceeded, or any
                other conflict returned by appointments.service.
            BookingNotFoundError: professional or service does not exist.
        """
        try:
            appt = appointment_svc.create_appointment(
                db,
                company_id,
                AppointmentCreate(
                    professional_id=intent.professional_id,
                    client_id=intent.customer_id,
                    start_at=intent.start_at,
                    services=[ServiceRequest(service_id=intent.service_id)],
                    idempotency_key=intent.idempotency_key,
                ),
                user_id=None,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) is not None:
                raise _http_exc_to_domain(exc) from exc
            raise

        return BookingResult(
            appointment_id=appt.id,
            service_name=appt.services[0].service_name if appt.services else "",
            professional_name=appt.professional.name if appt.professional else "",
            start_at=appt.start_at,
            end_at=appt.end_at,
            total_amount=appt.total_amount,
        )

    @staticmethod
    def cancel(
        db: Session,
        company_id: UUID,
        appointment_id: UUID,
        reason: str | None = None,
    ) -> CancelResult:
        """
        Cancel an appointment.

        Raises:
            BookingNotFoundError: appointment does not exist.
        PolicyViolationError from appointments.service propagates unchanged.
        """
        try:
            appt = appointment_svc.cancel_appointment(
                db, company_id, appointment_id, user_id=None, reason=reason
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) is not None:
                raise _http_exc_to_domain(exc) from exc
            raise

        return CancelResult(
            appointment_id=appt.id,
            cancelled_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def reschedule(
        db: Session,
        company_id: UUID,
        appointment_id: UUID,
        new_start_at: datetime,
    ) -> RescheduleResult:
        """
        Reschedule an appointment to a new slot.

        Raises:
            SlotUnavailableError: new slot is already taken.
            BookingNotFoundError: appointment does not exist.
        PolicyViolationError from appointments.service propagates unchanged.
        """
        try:
            appt = appointment_svc.reschedule_appointment(
                db,
                company_id,
                appointment_id,
                RescheduleRequest(start_at=new_start_at),
                user_id=None,
            )
        except Exception as exc:
            if getattr(exc, "status_code", None) is not None:
                raise _http_exc_to_domain(exc) from exc
            raise

        return RescheduleResult(
            appointment_id=appt.id,
            new_start_at=appt.start_at,
            new_end_at=appt.end_at,
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_active_bookings(
        db: Session,
        company_id: UUID,
        customer_id: UUID,
    ) -> list[BookingResult]:
        """Return all active (non-cancelled) appointments for a customer."""
        appointments = appointment_svc.list_active_by_client(db, company_id, customer_id)
        return [
            BookingResult(
                appointment_id=a.id,
                service_name=a.services[0].service_name if a.services else "",
                professional_name=a.professional.name if a.professional else "",
                start_at=a.start_at,
                end_at=a.end_at,
                total_amount=a.total_amount,
            )
            for a in appointments
        ]
