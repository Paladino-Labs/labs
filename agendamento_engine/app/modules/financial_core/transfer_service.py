"""Transfer Service — Sprint 7.

create_transfer: cria Transfer com 2 Movements atômicos (TRANSFER_OUT + TRANSFER_IN).
Não cria Entry — Transfer é movimentação, não fato econômico.
Falha no 2o Movement → rollback completo (exceção propaga, chamador faz rollback).
EventBus.publish chamado após commit, nunca dentro da transação.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.transfer import Transfer
from app.infrastructure.event_bus import DomainEvent, event_bus
from app.modules.financial_core.service import _record_movement, get_account


def create_transfer(
    from_account_id: UUID,
    to_account_id: UUID,
    amount: Decimal,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
    notes: Optional[str] = None,
) -> Transfer:
    """Cria transferência atômica entre duas contas do mesmo tenant.

    Única transação de banco:
      INSERT Transfer (REQUESTED)
      _record_movement(TRANSFER_OUT, from_account)
      _record_movement(TRANSFER_IN, to_account)
      Transfer.status = COMPLETED

    Sem Entry — Transfer é movimentação, não fato econômico.
    Falha em qualquer passo → exceção propaga, rollback é responsabilidade do chamador.
    """
    if from_account_id == to_account_id:
        raise HTTPException(status_code=422, detail="Conta de origem e destino devem ser diferentes")

    # Valida que ambas as contas pertencem ao tenant
    get_account(from_account_id, company_id, db)
    get_account(to_account_id, company_id, db)

    transfer = Transfer(
        company_id=company_id,
        from_account_id=from_account_id,
        to_account_id=to_account_id,
        amount=amount,
        status="REQUESTED",
        notes=notes,
    )
    db.add(transfer)
    db.flush()  # garante transfer_id antes dos movements

    now = datetime.now(timezone.utc)
    source_type = "transfer"
    source_id = transfer.transfer_id

    # TRANSFER_OUT da conta de origem
    _record_movement(
        account_id=from_account_id,
        type="TRANSFER_OUT",
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        transfer_id=transfer.transfer_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    # TRANSFER_IN na conta de destino — se falhar, a exceção propaga e o chamador faz rollback
    _record_movement(
        account_id=to_account_id,
        type="TRANSFER_IN",
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        transfer_id=transfer.transfer_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    transfer.status = "COMPLETED"
    transfer.completed_at = now

    db.commit()
    db.refresh(transfer)

    # EventBus após commit — best-effort, nunca dentro da transação
    event_bus.publish(DomainEvent(
        event_id=uuid.uuid4(),
        event_type="financial_core.transfer_completed",
        occurred_at=now,
        company_id=company_id,
        idempotency_key=f"transfer_completed:{transfer.transfer_id}",
        actor={"type": "TENANT_USER", "id": str(actor_id)},
        payload={
            "transfer_id": str(transfer.transfer_id),
            "from_account_id": str(from_account_id),
            "to_account_id": str(to_account_id),
            "amount": str(amount),
        },
    ))

    return transfer


def list_transfers(company_id: UUID, db: Session) -> list[Transfer]:
    return (
        db.query(Transfer)
        .filter(Transfer.company_id == company_id)
        .order_by(Transfer.requested_at.desc())
        .all()
    )
