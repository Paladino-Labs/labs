"""
Router do módulo Schedule Exceptions — Sprint 10.

Endpoints:
    GET    /schedule/exceptions/{professional_id}
    POST   /schedule/exceptions
    DELETE /schedule/exceptions/{id}
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_company_id, get_current_user
from app.infrastructure.db.session import get_db
from app.modules.schedule_exceptions import service as exc_service
from app.modules.schedule_exceptions.schemas import (
    ScheduleExceptionCreate,
    ScheduleExceptionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/schedule", tags=["schedule"])


@router.get(
    "/exceptions/{professional_id}",
    response_model=list[ScheduleExceptionResponse],
)
def list_exceptions(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return exc_service.list_exceptions(
        professional_id=professional_id,
        company_id=company_id,
        db=db,
    )


@router.post(
    "/exceptions",
    response_model=ScheduleExceptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_exception(
    body: ScheduleExceptionCreate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    exc = exc_service.create_exception(
        professional_id=body.professional_id,
        exception_date=body.exception_date,
        type=body.type,
        start_time=body.start_time,
        end_time=body.end_time,
        reason=body.reason,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(exc)
    return exc


@router.delete("/exceptions/{exception_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exception(
    exception_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    exc_service.delete_exception(
        exception_id=exception_id,
        company_id=company_id,
        db=db,
    )
    db.commit()
