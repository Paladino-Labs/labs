from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import WorkingHour, ScheduleBlock
from app.modules.schedule.schemas import WorkingHourCreate, ScheduleBlockCreate


# ── Working Hours ──────────────────────────────────────────────────────────────

def list_working_hours(db: Session, company_id: UUID, professional_id: UUID):
    return (
        db.query(WorkingHour)
        .filter(
            WorkingHour.company_id == company_id,
            WorkingHour.professional_id == professional_id,
        )
        .order_by(WorkingHour.weekday)
        .all()
    )


def upsert_working_hour(db: Session, company_id: UUID, data: WorkingHourCreate) -> WorkingHour:
    wh = db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == data.professional_id,
        WorkingHour.weekday == data.weekday,
    ).first()

    if wh:
        wh.opening_time = data.opening_time
        wh.closing_time = data.closing_time
        wh.is_active = data.is_active
    else:
        wh = WorkingHour(company_id=company_id, **data.model_dump())
        db.add(wh)

    db.commit()
    db.refresh(wh)
    return wh


# ── Schedule Blocks ────────────────────────────────────────────────────────────

def list_schedule_blocks(db: Session, company_id: UUID, professional_id: UUID):
    return (
        db.query(ScheduleBlock)
        .filter(
            ScheduleBlock.company_id == company_id,
            ScheduleBlock.professional_id == professional_id,
        )
        .order_by(ScheduleBlock.start_at)
        .all()
    )


def create_schedule_block(db: Session, company_id: UUID, data: ScheduleBlockCreate) -> ScheduleBlock:
    if data.end_at <= data.start_at:
        raise HTTPException(status_code=400, detail="end_at deve ser posterior a start_at")

    block = ScheduleBlock(company_id=company_id, **data.model_dump())
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def delete_schedule_block(db: Session, company_id: UUID, block_id: UUID) -> None:
    block = db.query(ScheduleBlock).filter(
        ScheduleBlock.id == block_id,
        ScheduleBlock.company_id == company_id,
    ).first()
    if not block:
        raise HTTPException(status_code=404, detail="Bloqueio não encontrado")
    # Soft: apenas marca como deleted não existe no modelo ainda,
    # então por ora fazemos delete físico (dados não são críticos).
    db.delete(block)
    db.commit()
