from uuid import UUID
from typing import List
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import WorkingHour, ScheduleBlock
from app.modules.schedule.schemas import WorkingHourCreate, WorkingHourPeriod, ScheduleBlockCreate


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


def replace_working_hours_for_day(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    weekday: int,
    periods: List[WorkingHourPeriod],
) -> List[WorkingHour]:
    """
    Substitui todos os períodos do dia por `periods` (estado completo).
    Lista vazia = dia de folga (DELETE sem INSERT).
    Valida: máx 3 períodos, start < end, sem sobreposição.
    """
    if len(periods) > 3:
        raise HTTPException(status_code=422, detail="Máximo de 3 períodos por dia")

    for p in periods:
        if p.start_time >= p.end_time:
            raise HTTPException(
                status_code=422,
                detail=f"start_time ({p.start_time}) deve ser anterior a end_time ({p.end_time})",
            )

    sorted_periods = sorted(periods, key=lambda x: x.start_time)
    for i in range(len(sorted_periods) - 1):
        if sorted_periods[i].end_time > sorted_periods[i + 1].start_time:
            raise HTTPException(status_code=422, detail="Períodos se sobrepõem")

    db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == professional_id,
        WorkingHour.weekday == weekday,
    ).delete(synchronize_session=False)

    new_records: List[WorkingHour] = []
    for p in sorted_periods:
        wh = WorkingHour(
            company_id=company_id,
            professional_id=professional_id,
            weekday=weekday,
            opening_time=p.start_time,
            closing_time=p.end_time,
            is_active=True,
        )
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
