"""Reconciliation Service — Sprint 7.

open_reconciliation: abre registro de reconciliação para uma conta.
close_reconciliation: fecha registro de reconciliação.
mark_movement_reconciled: vincula Movement a ReconciliationRecord via movement_reconciliations.
  Movement NÃO é alterado — append-only preservado.
list_unreconciled_movements: movements ainda não vinculados a nenhuma reconciliação.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.infrastructure.db.models.movement import Movement
from app.infrastructure.db.models.movement_reconciliation import MovementReconciliation
from app.infrastructure.db.models.reconciliation_record import ReconciliationRecord
from app.infrastructure.event_bus import DomainEvent, event_bus
from app.modules.financial_core.service import get_account


def open_reconciliation(
    account_id: UUID,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
    notes: str | None = None,
) -> ReconciliationRecord:
    """Abre um registro de reconciliação para a conta especificada."""
    get_account(account_id, company_id, db)

    record = ReconciliationRecord(
        company_id=company_id,
        account_id=account_id,
        status="OPEN",
        opened_by=actor_id,
        notes=notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    event_bus.publish(DomainEvent(
        event_id=uuid.uuid4(),
        event_type="financial_core.reconciliation_opened",
        occurred_at=datetime.now(timezone.utc),
        company_id=company_id,
        idempotency_key=f"reconciliation_opened:{record.reconciliation_id}",
        actor={"type": "TENANT_USER", "id": str(actor_id)},
        payload={"reconciliation_id": str(record.reconciliation_id)},
    ))

    return record


def close_reconciliation(
    reconciliation_id: UUID,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> ReconciliationRecord:
    """Fecha um registro de reconciliação (status OPEN → CLOSED)."""
    record = _get_reconciliation_or_404(reconciliation_id, company_id, db)

    if record.status == "CLOSED":
        raise HTTPException(status_code=422, detail="Reconciliação já está fechada")

    now = datetime.now(timezone.utc)
    record.status = "CLOSED"
    record.closed_at = now
    record.closed_by = actor_id

    db.commit()
    db.refresh(record)

    event_bus.publish(DomainEvent(
        event_id=uuid.uuid4(),
        event_type="financial_core.reconciliation_closed",
        occurred_at=now,
        company_id=company_id,
        idempotency_key=f"reconciliation_closed:{record.reconciliation_id}",
        actor={"type": "TENANT_USER", "id": str(actor_id)},
        payload={"reconciliation_id": str(record.reconciliation_id)},
    ))

    return record


def mark_movement_reconciled(
    movement_id: UUID,
    reconciliation_id: UUID,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> MovementReconciliation:
    """Vincula Movement a ReconciliationRecord via tabela de vínculo.

    Movement permanece 100% append-only — nenhum campo de Movement é alterado.
    """
    # Valida existência do movement no tenant
    movement = (
        db.query(Movement)
        .filter(Movement.movement_id == movement_id, Movement.company_id == company_id)
        .first()
    )
    if not movement:
        raise HTTPException(status_code=404, detail="Movement não encontrado")

    # Valida existência da reconciliação no tenant
    record = _get_reconciliation_or_404(reconciliation_id, company_id, db)
    if record.status == "CLOSED":
        raise HTTPException(status_code=422, detail="Não é possível reconciliar movement em reconciliação fechada")

    # Verifica se já está vinculado
    existing = (
        db.query(MovementReconciliation)
        .filter(
            MovementReconciliation.movement_id == movement_id,
            MovementReconciliation.reconciliation_id == reconciliation_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Movement já reconciliado nesta reconciliação")

    link = MovementReconciliation(
        company_id=company_id,
        movement_id=movement_id,
        reconciliation_id=reconciliation_id,
        reconciled_by=actor_id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


def list_unreconciled_movements(
    account_id: UUID,
    company_id: UUID,
    db: Session,
) -> list[Movement]:
    """Retorna movements da conta que ainda não foram vinculados a nenhuma reconciliação.

    LEFT JOIN movement_reconciliations WHERE mr.id IS NULL
    """
    result = (
        db.query(Movement)
        .outerjoin(
            MovementReconciliation,
            Movement.movement_id == MovementReconciliation.movement_id,
        )
        .filter(
            Movement.account_id == account_id,
            Movement.company_id == company_id,
            MovementReconciliation.id.is_(None),
        )
        .order_by(Movement.occurred_at.desc())
        .all()
    )
    return result


def _get_reconciliation_or_404(
    reconciliation_id: UUID,
    company_id: UUID,
    db: Session,
) -> ReconciliationRecord:
    record = (
        db.query(ReconciliationRecord)
        .filter(
            ReconciliationRecord.reconciliation_id == reconciliation_id,
            ReconciliationRecord.company_id == company_id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Reconciliação não encontrada")
    return record
