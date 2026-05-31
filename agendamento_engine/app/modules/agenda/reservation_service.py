"""
ReservationService — Sprint 10.

Gerencia o ciclo de vida de Reservations (SOFT → FIRME) com EXCLUDE USING gist
para garantir exclusividade de slot via banco de dados.

Regras críticas:
  - type (SOFT|FIRME) é imutável após criação.
  - promote_to_firme usa db.flush() entre PROMOTED e INSERT FIRME para liberar
    o EXCLUDE antes do novo INSERT.
  - expire_soft_reservation emite via Celery task (fluxo crítico), não EventBus.
  - Overbooking manual: apenas OWNER/ADMIN; reason obrigatório; record_sensitive_action.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.db.models.appointment import Appointment
from app.infrastructure.db.models.direct_occupancy import DirectOccupancy
from app.infrastructure.db.models.reservation import Reservation
from app.infrastructure.db.models.tenant_config import TenantConfig


class SlotUnavailableError(HTTPException):
    def __init__(self, detail: str = "Slot indisponível — conflito de reserva"):
        super().__init__(status_code=409, detail=detail)


def _get_ttl(company_id: UUID, db: Session) -> int:
    """Retorna soft_reservation_ttl_min do TenantConfig ou default 15."""
    cfg = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
    if cfg is not None:
        return cfg.soft_reservation_ttl_min
    return 15


def create_soft_reservation(
    professional_id: UUID,
    start_at: datetime,
    end_at: datetime,
    ttl_minutes: int | None,
    company_id: UUID,
    db: Session,
) -> Reservation:
    """
    Cria reserva SOFT ACTIVE com expires_at = now() + ttl_minutes.
    Se o EXCLUDE viola, levanta SlotUnavailableError (HTTP 409).
    ttl_minutes usa TenantConfig.soft_reservation_ttl_min (default 15) quando None.
    """
    if ttl_minutes is None:
        ttl_minutes = _get_ttl(company_id, db)

    now = datetime.now(timezone.utc)
    reservation = Reservation(
        reservation_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=professional_id,
        start_at=start_at,
        end_at=end_at,
        type="SOFT",
        status="ACTIVE",
        expires_at=now + timedelta(minutes=ttl_minutes),
    )
    db.add(reservation)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise SlotUnavailableError()
    return reservation


def promote_to_firme(
    reservation_id: UUID,
    appointment_id: UUID,
    company_id: UUID,
    db: Session,
) -> Reservation:
    """
    Promoção SOFT → FIRME atômica em única transação:
      1. soft.status = 'PROMOTED'  (sai do EXCLUDE)
      2. db.flush()                (libera constraint antes do INSERT)
      3. INSERT Reservation FIRME ACTIVE no mesmo slot
    Falha no INSERT FIRME → rollback; SOFT volta a ACTIVE (transação não commitada).
    """
    soft = (
        db.query(Reservation)
        .filter(
            Reservation.reservation_id == reservation_id,
            Reservation.company_id == company_id,
            Reservation.type == "SOFT",
            Reservation.status == "ACTIVE",
        )
        .with_for_update()
        .first()
    )
    if soft is None:
        raise HTTPException(status_code=404, detail="Reserva SOFT ativa não encontrada")

    soft.status = "PROMOTED"
    db.flush()  # libera o EXCLUDE antes do INSERT FIRME

    firme = Reservation(
        reservation_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=soft.professional_id,
        start_at=soft.start_at,
        end_at=soft.end_at,
        type="FIRME",
        status="ACTIVE",
        appointment_id=appointment_id,
        expires_at=None,
    )
    db.add(firme)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise SlotUnavailableError("Falha ao criar reserva FIRME — slot ocupado")
    return firme


def release_reservation(
    reservation_id: UUID,
    company_id: UUID,
    db: Session,
) -> None:
    """Marca a reserva como RELEASED."""
    reservation = (
        db.query(Reservation)
        .filter(
            Reservation.reservation_id == reservation_id,
            Reservation.company_id == company_id,
        )
        .first()
    )
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reserva não encontrada")
    reservation.status = "RELEASED"
    db.flush()


def expire_soft_reservation(
    reservation_id: UUID,
    company_id: UUID,
    db: Session,
) -> None:
    """
    Marca a reserva como EXPIRED e emite agenda.soft_reservation.expired
    via Celery task direta (fluxo crítico — não via EventBus best-effort).
    """
    reservation = (
        db.query(Reservation)
        .filter(
            Reservation.reservation_id == reservation_id,
            Reservation.company_id == company_id,
        )
        .first()
    )
    if reservation is None:
        return  # idempotente — reserva não encontrada

    if reservation.status != "ACTIVE":
        return  # já processada — idempotente

    reservation.status = "EXPIRED"
    db.flush()

    # Emite via Celery task (crítico: não usar EventBus best-effort).
    # importlib.import_module verifica sys.modules primeiro, o que permite
    # que testes substituam o módulo via patch.dict(sys.modules, ...).
    import importlib
    _expire_mod = importlib.import_module("app.workers.tasks.expire_reservations")
    _expire_mod.dispatch_soft_reservation_expired.delay(
        str(reservation_id), str(company_id)
    )


def create_firme_direct(
    professional_id: UUID,
    start_at: datetime,
    end_at: datetime,
    appointment_id: UUID,
    company_id: UUID,
    db: Session,
) -> Reservation:
    """Walk-in: INSERT FIRME ACTIVE direto, sem SOFT intermediária."""
    firme = Reservation(
        reservation_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=professional_id,
        start_at=start_at,
        end_at=end_at,
        type="FIRME",
        status="ACTIVE",
        appointment_id=appointment_id,
        expires_at=None,
    )
    db.add(firme)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise SlotUnavailableError("Slot ocupado para reserva FIRME direta")
    return firme


def open_direct_occupancy(
    professional_id: UUID,
    start_at: datetime,
    end_at: datetime,
    reason: str,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> DirectOccupancy:
    """Cria um bloqueio manual de agenda por OWNER/ADMIN/OPERATOR."""
    occupancy = DirectOccupancy(
        occupancy_id=uuid.uuid4(),
        company_id=company_id,
        professional_id=professional_id,
        start_at=start_at,
        end_at=end_at,
        reason=reason,
        opened_by=actor_id,
    )
    db.add(occupancy)
    db.flush()
    return occupancy


def close_direct_occupancy(
    occupancy_id: UUID,
    company_id: UUID,
    db: Session,
) -> DirectOccupancy:
    """Fecha um bloqueio manual de agenda."""
    occupancy = (
        db.query(DirectOccupancy)
        .filter(
            DirectOccupancy.occupancy_id == occupancy_id,
            DirectOccupancy.company_id == company_id,
        )
        .first()
    )
    if occupancy is None:
        raise HTTPException(status_code=404, detail="Ocupação direta não encontrada")
    if occupancy.closed_at is not None:
        raise HTTPException(status_code=409, detail="Ocupação já encerrada")
    occupancy.closed_at = datetime.now(timezone.utc)
    db.flush()
    return occupancy
