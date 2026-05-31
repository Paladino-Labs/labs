"""
Router do módulo Agenda — Sprint 10.

Endpoints:
    POST  /agenda/soft-reservation
    POST  /agenda/soft-reservation/{id}/promote
    POST  /agenda/soft-reservation/{id}/release
    POST  /agenda/firme-direct              OWNER/ADMIN/OPERATOR
    POST  /agenda/direct-occupancy          OWNER/ADMIN/OPERATOR
    PUT   /agenda/direct-occupancy/{id}/close
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_company_id, get_current_user, require_role
from app.core.audit.sensitive_context import record_sensitive_action, SensitiveAuditContext
from app.infrastructure.db.session import get_db
from app.modules.agenda import reservation_service
from app.modules.agenda.schemas import (
    DirectOccupancyCreate,
    DirectOccupancyResponse,
    FirmeDirectCreate,
    PromoteRequest,
    ReservationResponse,
    SoftReservationCreate,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agenda", tags=["agenda"])

_owner_admin_operator = require_role("OWNER", "ADMIN", "OPERATOR", "PLATFORM_OWNER")


@router.post("/soft-reservation", response_model=ReservationResponse, status_code=201)
def create_soft_reservation(
    body: SoftReservationCreate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    reservation = reservation_service.create_soft_reservation(
        professional_id=body.professional_id,
        start_at=body.start_at,
        end_at=body.end_at,
        ttl_minutes=body.ttl_minutes,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(reservation)
    return reservation


@router.post("/soft-reservation/{reservation_id}/promote", response_model=ReservationResponse)
def promote_soft_reservation(
    reservation_id: UUID,
    body: PromoteRequest,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    firme = reservation_service.promote_to_firme(
        reservation_id=reservation_id,
        appointment_id=body.appointment_id,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(firme)
    return firme


@router.post("/soft-reservation/{reservation_id}/release", status_code=204)
def release_soft_reservation(
    reservation_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    reservation_service.release_reservation(
        reservation_id=reservation_id,
        company_id=company_id,
        db=db,
    )
    db.commit()


@router.post("/firme-direct", response_model=ReservationResponse, status_code=201)
def create_firme_direct(
    body: FirmeDirectCreate,
    user=Depends(_owner_admin_operator),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    record_sensitive_action(
        ctx=SensitiveAuditContext(
            actor_id=user.id,
            actor_role=user.role,
            action="firme_direct_overbooking",
            resource_type="reservation",
            company_id=company_id,
            reason=body.reason,
        ),
        db=db,
    )

    reservation = reservation_service.create_firme_direct(
        professional_id=body.professional_id,
        start_at=body.start_at,
        end_at=body.end_at,
        appointment_id=body.appointment_id,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(reservation)
    return reservation


@router.post("/direct-occupancy", response_model=DirectOccupancyResponse, status_code=201)
def open_direct_occupancy(
    body: DirectOccupancyCreate,
    user=Depends(_owner_admin_operator),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    occupancy = reservation_service.open_direct_occupancy(
        professional_id=body.professional_id,
        start_at=body.start_at,
        end_at=body.end_at,
        reason=body.reason,
        actor_id=user.id,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(occupancy)
    return occupancy


@router.put("/direct-occupancy/{occupancy_id}/close", response_model=DirectOccupancyResponse)
def close_direct_occupancy(
    occupancy_id: UUID,
    user=Depends(_owner_admin_operator),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    occupancy = reservation_service.close_direct_occupancy(
        occupancy_id=occupancy_id,
        company_id=company_id,
        db=db,
    )
    db.commit()
    db.refresh(occupancy)
    return occupancy
