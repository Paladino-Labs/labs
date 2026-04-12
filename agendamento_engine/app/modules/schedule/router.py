from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.modules.schedule import schemas, service as svc

router = APIRouter(prefix="/schedule", tags=["schedule"])


# ── Working Hours ──────────────────────────────────────────────────────────────

@router.get("/working-hours/{professional_id}", response_model=List[schemas.WorkingHourResponse])
def list_working_hours(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_working_hours(db, company_id, professional_id)


@router.post("/working-hours", response_model=schemas.WorkingHourResponse)
def upsert_working_hour(
    body: schemas.WorkingHourCreate,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return svc.upsert_working_hour(db, user.company_id, body)


# ── Schedule Blocks ────────────────────────────────────────────────────────────

@router.get("/blocks/{professional_id}", response_model=List[schemas.ScheduleBlockResponse])
def list_schedule_blocks(
    professional_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return svc.list_schedule_blocks(db, company_id, professional_id)


@router.post("/blocks", response_model=schemas.ScheduleBlockResponse, status_code=201)
def create_schedule_block(
    body: schemas.ScheduleBlockCreate,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    return svc.create_schedule_block(db, user.company_id, body)


@router.delete("/blocks/{block_id}", status_code=204)
def delete_schedule_block(
    block_id: UUID,
    user=Depends(require_admin),
    db: Session = Depends(get_db),
):
    svc.delete_schedule_block(db, user.company_id, block_id)
