from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.schedule.schemas import (
    ScheduleBlockCreate,
    ScheduleBlockOut,
    WorkingHourOut,
    WorkingHourUpsert,
)
from app.modules.schedule.service import (
    create_block,
    list_blocks,
    list_working_hours,
    upsert_working_hour,
)

router = APIRouter(tags=["Schedule"])


@router.get("/professionals/{professional_id}/working-hours", response_model=list[WorkingHourOut])
def get_working_hours(
    professional_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return list_working_hours(db, current_user.company_id, professional_id)


@router.put("/professionals/{professional_id}/working-hours/{weekday}", response_model=WorkingHourOut)
def put_working_hour(
    professional_id: UUID,
    weekday: int,
    data: WorkingHourUpsert,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    payload = data.model_copy(update={"weekday": weekday})
    return upsert_working_hour(db, current_user.company_id, professional_id, payload)


@router.get("/professionals/{professional_id}/schedule-blocks", response_model=list[ScheduleBlockOut])
def get_schedule_blocks(
    professional_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return list_blocks(db, current_user.company_id, professional_id)


@router.post("/professionals/{professional_id}/schedule-blocks", response_model=ScheduleBlockOut, status_code=201)
def post_schedule_block(
    professional_id: UUID,
    data: ScheduleBlockCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_block(db, current_user.company_id, professional_id, data)
