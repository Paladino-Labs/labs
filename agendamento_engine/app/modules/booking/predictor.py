"""
Predictive booking offer for returning customers.
 
Given a customer with completed appointments, suggests the same
service + professional with the next available slot.
 
Returns a clean PredictiveOfferResult — no text, no formatting,
no WhatsApp or HTTP concerns.
"""
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID
 
from sqlalchemy.orm import Session
 
from app.core.config import settings
from app.modules.appointments import service as appointment_svc
from app.modules.availability import service as availability_svc
from app.modules.booking.schemas import PredictiveOfferResult
 
logger = logging.getLogger(__name__)
 
 
def get_predictive_offer(
    db: Session,
    company_id: UUID,
    customer_id: UUID,
) -> PredictiveOfferResult | None:
    """
    Return a predictive booking offer for a returning customer, or None.
 
    Logic:
      1. Fetch the customer's last completed appointment.
      2. Check if the same professional + service has a slot in the next 7 days.
      3. Return a structured offer with TTL; return None if any step fails.
    """
    last_completed = appointment_svc.list_completed_by_client(
        db, company_id, customer_id, limit=1
    )
    if not last_completed:
        return None
 
    last_appt = last_completed[0]
    svc_id  = last_appt.services[0].service_id if last_appt.services else None
    prof_id = last_appt.professional_id
 
    if not svc_id or not prof_id:
        return None
 
    slots = availability_svc.get_next_available_slots(
        db, company_id, prof_id, svc_id, days=7, limit=1
    )
    if not slots:
        return None
 
    slot      = slots[0]
    svc_name  = last_appt.services[0].service_name
    prof_name = last_appt.professional.name if last_appt.professional else ""
 
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.BOT_PREDICTIVE_OFFER_TTL_MINUTES
    )
 
    return PredictiveOfferResult(
        service_id=svc_id,
        service_name=svc_name,
        professional_id=prof_id,
        professional_name=prof_name,
        slot_start_at=slot.start_at,
        slot_end_at=slot.end_at,
        expires_at=expires_at,
    )
