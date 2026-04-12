from datetime import datetime, timedelta, date, timezone
from uuid import UUID
from typing import List

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    WorkingHour, ScheduleBlock, Appointment, Service, Professional
)
from app.domain.constants.scheduling import SLOT_INTERVAL_MINUTES
from app.modules.availability.schemas import AvailableSlot


def get_next_available_slots(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    service_id: UUID,
    days: int = 3,
    limit: int = 6,
) -> List[AvailableSlot]:
    """
    Retorna os próximos <limit> slots disponíveis nos próximos <days> dias.
    Usado pelo bot nos estados ESCOLHENDO_PROFISSIONAL e OFERTA_RECORRENTE —
    quando o usuário ainda não escolheu uma data.
    """
    today = datetime.now(timezone.utc).date()
    collected: List[AvailableSlot] = []

    for offset in range(days):
        if len(collected) >= limit:
            break
        target = today + timedelta(days=offset)
        try:
            day_slots = get_available_slots(
                db, company_id, professional_id, service_id, target
            )
        except HTTPException:
            # Profissional pode não trabalhar neste dia — pular
            continue
        for slot in day_slots:
            if len(collected) >= limit:
                break
            collected.append(slot)

    return collected


def get_available_slots(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    service_id: UUID,
    target_date: date,
) -> List[AvailableSlot]:
    # Valida profissional
    professional = db.query(Professional).filter(
        Professional.id == professional_id,
        Professional.company_id == company_id,
        Professional.active == True,
    ).first()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    # Valida serviço
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.company_id == company_id,
        Service.active == True,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    duration = service.duration  # minutos

    # Busca horário de trabalho do dia
    weekday = target_date.weekday()  # 0=seg
    working_hour = db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == professional_id,
        WorkingHour.weekday == weekday,
        WorkingHour.is_active == True,
    ).first()

    if not working_hour:
        return []

    # Janela do dia — sempre em UTC para comparar corretamente com o banco
    day_start = datetime.combine(target_date, working_hour.opening_time, tzinfo=timezone.utc)
    day_end   = datetime.combine(target_date, working_hour.closing_time, tzinfo=timezone.utc)

    # Agendamentos existentes no dia (apenas ativos)
    day_appointments = db.query(Appointment).filter(
        Appointment.company_id == company_id,
        Appointment.professional_id == professional_id,
        Appointment.start_at >= day_start,
        Appointment.start_at < day_end,
        Appointment.status.notin_(["CANCELLED", "NO_SHOW"]),
    ).all()

    # Bloqueios manuais no dia
    blocks = db.query(ScheduleBlock).filter(
        ScheduleBlock.company_id == company_id,
        ScheduleBlock.professional_id == professional_id,
        ScheduleBlock.start_at < day_end,
        ScheduleBlock.end_at > day_start,
    ).all()

    # Gera slots candidatos
    slots: List[AvailableSlot] = []
    cursor = day_start
    now = datetime.now(timezone.utc)  # timezone-aware; datetime.utcnow() foi depreciado

    while cursor + timedelta(minutes=duration) <= day_end:
        slot_end = cursor + timedelta(minutes=duration)

        # Ignora slots no passado
        if cursor <= now:
            cursor += timedelta(minutes=SLOT_INTERVAL_MINUTES)
            continue

        # Verifica conflito com agendamentos
        conflict = any(
            not (slot_end <= a.start_at or cursor >= a.end_at)
            for a in day_appointments
        )

        # Verifica conflito com bloqueios
        if not conflict:
            conflict = any(
                not (slot_end <= b.start_at or cursor >= b.end_at)
                for b in blocks
            )

        if not conflict:
            slots.append(AvailableSlot(
                start_at=cursor,
                end_at=slot_end,
                professional_id=professional_id,
                professional_name=professional.name,
            ))

        cursor += timedelta(minutes=SLOT_INTERVAL_MINUTES)

    return slots
