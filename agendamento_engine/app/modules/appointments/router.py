from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_user, get_current_company_id
from app.infrastructure.db.models import User
from app.modules.appointments import schemas, service as svc
from app.modules.appointments.polices import PolicyViolationError

router = APIRouter(prefix="/appointments", tags=["appointments"])


def _handle_policy_error(e: PolicyViolationError) -> JSONResponse:
    """Converte PolicyViolationError em HTTP 422 com código estruturado."""
    return JSONResponse(
        status_code=422,
        content={"code": e.code, "detail": e.detail},
    )


@router.get("/", response_model=List[schemas.AppointmentResponse])
def list_appointments(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_appointments(db, company_id)


@router.post("/", response_model=schemas.AppointmentResponse, status_code=201)
def create_appointment(
    body: schemas.AppointmentCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return svc.create_appointment(db, user.company_id, body, user.id)


@router.get("/{appointment_id}", response_model=schemas.AppointmentResponse)
def get_appointment(
    appointment_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.get_appointment_or_404(db, company_id, appointment_id)


@router.patch("/{appointment_id}/cancel", response_model=schemas.AppointmentResponse)
def cancel_appointment(
    appointment_id: UUID,
    body: schemas.CancelRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return svc.cancel_appointment(db, user.company_id, appointment_id, user.id, body.reason)
    except PolicyViolationError as e:
        return _handle_policy_error(e)


@router.patch("/{appointment_id}/reschedule", response_model=schemas.AppointmentResponse)
def reschedule_appointment(
    appointment_id: UUID,
    body: schemas.RescheduleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        return svc.reschedule_appointment(db, user.company_id, appointment_id, body, user.id)
    except PolicyViolationError as e:
        return _handle_policy_error(e)
