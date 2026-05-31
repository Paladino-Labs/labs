"""
ScheduleExceptionService — Sprint 10.

Gerencia exceções de agenda por profissional:
  SUBSTITUTIVE — substitui horário padrão (start_time/end_time nullable = dia de folga)
  ADDITIVE     — adiciona horário extra além do padrão
"""
from __future__ import annotations

import uuid
from datetime import date, time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.db.models.schedule_exception import ScheduleException


def list_exceptions(
    professional_id: UUID,
    company_id: UUID,
    db: Session,
) -> list[ScheduleException]:
    return (
        db.query(ScheduleException)
        .filter(
            ScheduleException.professional_id == professional_id,
            ScheduleException.company_id == company_id,
        )
        .order_by(ScheduleException.exception_date)
        .all()
    )


def create_exception(
    professional_id: UUID,
    exception_date: date,
    type: str,
    start_time: time | None,
    end_time: time | None,
    reason: str | None,
    company_id: UUID,
    db: Session,
) -> ScheduleException:
    exc = ScheduleException(
        exception_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=professional_id,
        exception_date=exception_date,
        type=type,
        start_time=start_time,
        end_time=end_time,
        reason=reason,
    )
    db.add(exc)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe uma exceção deste tipo para o profissional nesta data",
        )
    return exc


def delete_exception(
    exception_id: UUID,
    company_id: UUID,
    db: Session,
) -> None:
    exc = (
        db.query(ScheduleException)
        .filter(
            ScheduleException.exception_id == exception_id,
            ScheduleException.company_id == company_id,
        )
        .first()
    )
    if exc is None:
        raise HTTPException(status_code=404, detail="Exceção de agenda não encontrada")
    db.delete(exc)
    db.flush()
