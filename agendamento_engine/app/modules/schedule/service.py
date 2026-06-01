from uuid import UUID
from typing import List
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
        .order_by(WorkingHour.weekday, WorkingHour.opening_time)
        .all()
    )


def upsert_working_hour(
    db: Session, company_id: UUID, periods: List[WorkingHourCreate]
) -> List[WorkingHour]:
    """
    Substitui todos os horários do dia (professional_id + weekday) pelos novos.
    Aceita uma lista de períodos — permite manhã + tarde no mesmo dia.
    Cada chamada representa o estado COMPLETO do dia; registros anteriores são deletados.
    """
    if not periods:
        return []

    professional_id = periods[0].professional_id
    weekday = periods[0].weekday

    db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == professional_id,
        WorkingHour.weekday == weekday,
    ).delete(synchronize_session=False)

    new_records: List[WorkingHour] = []
    for data in periods:
        wh = WorkingHour(company_id=company_id, **data.model_dump())
        db.add(wh)
        new_records.append(wh)

    db.commit()
    for wh in new_records:
        db.refresh(wh)
    return new_records


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
