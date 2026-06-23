from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload, selectinload
from sqlalchemy.exc import IntegrityError

from app.infrastructure.db.models import (
    Appointment, Customer, Professional, Service, WorkingHour, ScheduleBlock, TenantConfig,
)
from app.domain.enums import AppointmentStatus, FinancialStatus
from app.modules.appointments.schemas import AppointmentCreate, RescheduleRequest
from app.modules.appointments.snapshots import build_snapshots
from app.modules.appointments.transitions import transition
from app.modules.appointments.polices import (
    PolicyViolationError,
    CANCELLATION_TOO_LATE, RESCHEDULE_TOO_LATE,
    check_cancellation_policy, check_reschedule_policy,
)
from app.modules.appointments.manage_tokens import issue_manage_token
from app.modules.notifications import (
    send_booking_confirmation,
    send_reschedule_confirmation,
)
from app.core.config import settings


def _publish_slot_released(appointment: Appointment, event_type: str) -> None:
    """Emite appointment.cancelled/rescheduled via EventBus — best-effort,
    consumido pela fila de espera (Sprint G). Falha não afeta a operação."""
    import logging
    import uuid as _uuid

    from app.infrastructure.event_bus import DomainEvent, event_bus

    try:
        service_ids = [
            str(svc.service_id) for svc in (appointment.services or [])
            if svc.service_id is not None
        ]
        event_bus.publish(DomainEvent(
            event_id=_uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=appointment.company_id,
            idempotency_key=f"{event_type}.slot_released:{appointment.id}:{appointment.version}",
            actor={"type": "SYSTEM", "id": None},
            payload={
                "appointment_id": str(appointment.id),
                "professional_id": str(appointment.professional_id) if appointment.professional_id else None,
                "service_ids": service_ids,
                "customer_id": str(appointment.client_id) if appointment.client_id else None,
                "company_id": str(appointment.company_id),
            },
        ))
    except Exception:
        logging.getLogger(__name__).exception(
            "_publish_slot_released: falha ao publicar %s appointment_id=%s",
            event_type, appointment.id,
        )


def _assert_slot_available(
    db: Session,
    company_id: UUID,
    professional_id: UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_appointment_id: UUID | None = None,
) -> None:
    """
    Defense-in-depth: verifica se o slot [start_at, end_at) está disponível
    antes de tentar persistir. Levanta 422 para restrições de horário e 409
    para conflitos com agendamentos ou bloqueios existentes.
    """
    weekday = start_at.weekday()

    # 1. Profissional trabalha neste dia?
    working_hour = db.query(WorkingHour).filter(
        WorkingHour.company_id == company_id,
        WorkingHour.professional_id == professional_id,
        WorkingHour.weekday == weekday,
        WorkingHour.is_active == True,
    ).first()

    if not working_hour:
        raise HTTPException(
            status_code=422,
            detail="Profissional não atende neste dia da semana",
        )

    # 2. Slot dentro da janela de trabalho?
    config = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
    tz_name = (getattr(config, "timezone", None) or "America/Sao_Paulo")
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo("America/Sao_Paulo")

    slot_date = start_at.astimezone(tz).date()
    day_start = datetime.combine(slot_date, working_hour.opening_time, tzinfo=tz).astimezone(timezone.utc)
    day_end   = datetime.combine(slot_date, working_hour.closing_time, tzinfo=tz).astimezone(timezone.utc)

    if start_at < day_start or end_at > day_end:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Horário fora da janela de trabalho do profissional "
                f"({working_hour.opening_time.strftime('%H:%M')}–"
                f"{working_hour.closing_time.strftime('%H:%M')} horário local)"
            ),
        )

    # 3. Conflito com agendamentos ativos?
    overlap_q = db.query(Appointment).filter(
        Appointment.company_id == company_id,
        Appointment.professional_id == professional_id,
        Appointment.status.notin_(["CANCELLED", "NO_SHOW"]),
        Appointment.start_at < end_at,
        Appointment.end_at > start_at,
    )
    if exclude_appointment_id:
        overlap_q = overlap_q.filter(Appointment.id != exclude_appointment_id)

    if overlap_q.first():
        raise HTTPException(
            status_code=409,
            detail="Horário já ocupado por outro agendamento",
        )

    # 4. Conflito com bloqueios manuais?
    block = db.query(ScheduleBlock).filter(
        ScheduleBlock.company_id == company_id,
        ScheduleBlock.professional_id == professional_id,
        ScheduleBlock.start_at < end_at,
        ScheduleBlock.end_at > start_at,
    ).first()

    if block:
        raise HTTPException(
            status_code=409,
            detail="Horário bloqueado na agenda do profissional",
        )


def list_appointments(
    db: Session,
    company_id: UUID,
    page: int = 1,
    page_size: int = 50,
    start_after: datetime | None = None,
    start_before: datetime | None = None,
    customer_id: UUID | None = None,
    professional_id: UUID | None = None,
):
    query = (
        db.query(Appointment)
        .options(
            selectinload(Appointment.services),
            joinedload(Appointment.professional),
            joinedload(Appointment.customer),
        )
        .filter(Appointment.company_id == company_id)
    )
    if start_after is not None:
        query = query.filter(Appointment.start_at >= start_after)
    if start_before is not None:
        query = query.filter(Appointment.start_at < start_before)
    if customer_id is not None:
        query = query.filter(Appointment.client_id == customer_id)
    if professional_id is not None:
        query = query.filter(Appointment.professional_id == professional_id)
    return (
        query.order_by(Appointment.start_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )


def get_appointment_or_404(db: Session, company_id: UUID, appointment_id: UUID) -> Appointment:
    a = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.company_id == company_id,
    ).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return a


def list_active_by_client(
    db: Session, company_id: UUID, client_id: UUID
) -> list[Appointment]:
    now = datetime.now(timezone.utc)
    return (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == client_id,
            Appointment.status.in_(["SCHEDULED", "IN_PROGRESS"]),
            Appointment.start_at > now,
        )
        .order_by(Appointment.start_at.asc())
        .all()
    )


def list_completed_by_client(
    db: Session, company_id: UUID, client_id: UUID, limit: int = 1
) -> list[Appointment]:
    return (
        db.query(Appointment)
        .filter(
            Appointment.company_id == company_id,
            Appointment.client_id == client_id,
            Appointment.status == "COMPLETED",
        )
        .order_by(Appointment.start_at.desc())
        .limit(limit)
        .all()
    )


def create_appointment(
    db: Session, company_id: UUID, data: AppointmentCreate, user_id: UUID | None = None
) -> Appointment:
    # Valida profissional
    professional = db.query(Professional).filter(
        Professional.id == data.professional_id,
        Professional.company_id == company_id,
        Professional.active == True,
    ).first()
    if not professional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    # Valida cliente
    customer = db.query(Customer).filter(
        Customer.id == data.client_id,
        Customer.company_id == company_id,
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    # Valida e carrega serviços
    service_ids = [s.service_id for s in data.services]
    services = db.query(Service).filter(
        Service.id.in_(service_ids),
        Service.company_id == company_id,
        Service.active == True,
    ).all()

    if len(services) != len(service_ids):
        raise HTTPException(status_code=404, detail="Um ou mais serviços não encontrados")

    # Constrói snapshots e calcula valores
    snapshots, subtotal, total_minutes = build_snapshots(services)
    end_at = data.start_at + timedelta(minutes=total_minutes)

    # Defense in depth: verifica disponibilidade antes do INSERT
    _assert_slot_available(db, company_id, data.professional_id, data.start_at, end_at)

    appointment = Appointment(
        company_id=company_id,
        professional_id=data.professional_id,
        client_id=data.client_id,
        start_at=data.start_at,
        end_at=end_at,
        subtotal_amount=subtotal,
        discount_amount=Decimal("0"),
        total_amount=subtotal,
        total_commission=Decimal("0"),
        status=AppointmentStatus.SCHEDULED.value,
        financial_status=FinancialStatus.UNPAID.value,
        idempotency_key=data.idempotency_key,
    )

    for snap in snapshots:
        appointment.services.append(snap)

    # Link de gestão (Sprint B): hash persiste junto com o appointment;
    # o token cru vai apenas na mensagem de confirmação
    manage_token = issue_manage_token(appointment)

    db.add(appointment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Agendamento duplicado (idempotency_key já usado)")

    db.refresh(appointment)

    # Disparar confirmação via WhatsApp — fire-and-forget, nunca propaga erros
    send_booking_confirmation(db, appointment, manage_token=manage_token)

    return appointment


def cancel_appointment(
    db: Session, company_id: UUID, appointment_id: UUID,
    user_id: UUID | None = None, reason: str = None,
    skip_policy: bool = False,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)

    if not skip_policy:
        allowed, msg = check_cancellation_policy(
            start_at=appointment.start_at,
            now=datetime.now(timezone.utc),
            min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_CANCEL,
        )
        if not allowed:
            raise PolicyViolationError(code=CANCELLATION_TOO_LATE, detail=msg)

    transition(db, appointment, AppointmentStatus.CANCELLED, changed_by_id=user_id, note=reason)
    appointment.cancelled_at = datetime.now(timezone.utc)
    appointment.cancelled_by = user_id
    appointment.cancel_reason = reason
    db.commit()
    db.refresh(appointment)

    # Sinal: refund dentro da janela / retenção fora (Sprint 25) — best-effort,
    # no-op sem DepositPolicy. Não afeta o cancelamento já commitado.
    _apply_deposit_cancellation(db, appointment)

    # Slot liberado → fila de espera (Sprint G)
    _publish_slot_released(appointment, "appointment.cancelled")

    return appointment


def reschedule_appointment(
    db: Session, company_id: UUID, appointment_id: UUID,
    data: RescheduleRequest, user_id: UUID | None = None,
    skip_policy: bool = False,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)

    if AppointmentStatus(appointment.status).is_terminal:
        raise HTTPException(status_code=409, detail="Não é possível remarcar um agendamento encerrado")

    if not skip_policy:
        allowed, msg = check_reschedule_policy(
            start_at=appointment.start_at,
            now=datetime.now(timezone.utc),
            min_hours=settings.APPOINTMENT_MIN_HOURS_BEFORE_RESCHEDULE,
        )
        if not allowed:
            raise PolicyViolationError(code=RESCHEDULE_TOO_LATE, detail=msg)

    total_minutes = sum(int(s.duration_snapshot) for s in appointment.services)
    new_end_at = data.start_at + timedelta(minutes=total_minutes)

    _assert_slot_available(
        db, company_id, appointment.professional_id,
        data.start_at, new_end_at,
        exclude_appointment_id=appointment_id,
    )

    appointment.start_at = data.start_at
    appointment.end_at = new_end_at

    # Novo token de gestão — o link anterior deixa de funcionar (Sprint B)
    manage_token = issue_manage_token(appointment)

    db.commit()
    db.refresh(appointment)

    # Disparar confirmação de reagendamento — fire-and-forget
    send_reschedule_confirmation(db, appointment, manage_token=manage_token)

    # Slot anterior liberado → fila de espera (Sprint G)
    _publish_slot_released(appointment, "appointment.rescheduled")

    return appointment


def complete_appointment(
    db: Session, company_id: UUID, appointment_id: UUID,
    user_id: UUID | None = None,
    use_credit: bool = False,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)

    # Sprint 26: conclusão consumindo cota (pacote/assinatura). Consome ANTES da
    # transição — sem cota disponível → 409, o appointment não muda de estado.
    if use_credit:
        from app.modules.customer_credit import service as credit_service
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        service_id = appointment.services[0].service_id if appointment.services else None
        try:
            credit_service.consume_for_operation(
                customer_id=appointment.client_id,
                appointment_id=appointment.id,
                company_id=company_id,
                db=db,
                service_id=service_id,
            )
        except NoCreditAvailableError:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail="Nenhuma cota disponível para concluir este agendamento com crédito",
            )

    transition(db, appointment, AppointmentStatus.COMPLETED, changed_by_id=user_id,
               note="Concluído pelo painel")
    db.commit()
    db.refresh(appointment)

    # Sinal: reconhece o saldo restante como receita (Sprint 25) — best-effort,
    # no-op sem pagamento parcial confirmado. Não afeta o complete já commitado.
    _recognize_deposit_balance(db, appointment)

    return appointment


def mark_no_show(
    db: Session, company_id: UUID, appointment_id: UUID,
    user_id: UUID | None = None,
) -> Appointment:
    appointment = get_appointment_or_404(db, company_id, appointment_id)
    transition(db, appointment, AppointmentStatus.NO_SHOW, changed_by_id=user_id,
               note="No-show")
    db.commit()
    db.refresh(appointment)

    # Sinal: retém (default) ou estorna conforme DepositPolicy (Sprint 25) —
    # best-effort, no-op sem DepositPolicy.
    _apply_deposit_no_show(db, appointment)

    return appointment


def _recognize_deposit_balance(db: Session, appointment: Appointment) -> None:
    try:
        from app.modules.payments import deposit_service
        deposit_service.recognize_balance_on_completion(appointment, db)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_recognize_deposit_balance: falha (best-effort) appointment_id=%s",
            appointment.id,
        )


def _apply_deposit_cancellation(db: Session, appointment: Appointment) -> None:
    try:
        from app.modules.payments import deposit_service
        deposit_service.handle_cancellation_deposit(appointment, db)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_apply_deposit_cancellation: falha (best-effort) appointment_id=%s",
            appointment.id,
        )


def _apply_deposit_no_show(db: Session, appointment: Appointment) -> None:
    try:
        from app.modules.payments import deposit_service
        deposit_service.handle_no_show_deposit(appointment, db)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "_apply_deposit_no_show: falha (best-effort) appointment_id=%s",
            appointment.id,
        )