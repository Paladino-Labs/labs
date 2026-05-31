"""Cash Count Service — Sprint 7.

record_count: registra conferência de caixa.
  discrepancy = counted_amount - expected_amount (via compute_balance)
  Se ADJUSTED e discrepancy != 0:
    notes obrigatório (422 se ausente)
    Cria ajuste via FinancialCoreEngine.create_manual_adjustment
    Vincula cash_count.entry_id
  EventBus.publish após commit.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.cash_count import CashCount
from app.infrastructure.event_bus import DomainEvent, event_bus
from app.modules.financial_core import service as financial_core


def record_count(
    account_id: UUID,
    counted_amount: Decimal,
    resolution: str,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
    notes: str | None = None,
) -> CashCount:
    """Registra conferência de caixa.

    discrepancy = counted_amount - expected_amount (compute_balance)
    Se resolution=ADJUSTED e discrepancy != 0:
      notes obrigatório (422 se ausente)
      direction = ADDS se discrepancy > 0, SUBTRACTS se < 0
      Cria ajuste manual via FinancialCoreEngine.create_manual_adjustment
      cash_count.entry_id = entry gerada
    """
    if resolution not in ("ADJUSTED", "NO_ADJUSTMENT"):
        raise HTTPException(status_code=422, detail="resolution deve ser ADJUSTED ou NO_ADJUSTMENT")

    # Valida conta e calcula saldo esperado
    financial_core.get_account(account_id, company_id, db)
    expected_amount = financial_core.compute_balance(
        account_id=account_id,
        company_id=company_id,
        db=db,
    )

    discrepancy = counted_amount - expected_amount

    entry_id = None

    if resolution == "ADJUSTED" and discrepancy != Decimal("0"):
        if not notes or not notes.strip():
            raise HTTPException(
                status_code=422,
                detail="notes é obrigatório quando resolution=ADJUSTED e discrepancy != 0",
            )

        direction = "ADDS" if discrepancy > 0 else "SUBTRACTS"

        _movement, entry = financial_core.create_manual_adjustment(
            amount=abs(discrepancy),
            direction=direction,
            category="CONTAGEM_CAIXA",
            account_id=account_id,
            reason=notes,
            actor_id=actor_id,
            company_id=company_id,
            db=db,
        )
        entry_id = entry.entry_id

    cash_count = CashCount(
        company_id=company_id,
        account_id=account_id,
        expected_amount=expected_amount,
        counted_amount=counted_amount,
        discrepancy=discrepancy,
        resolution=resolution,
        notes=notes,
        entry_id=entry_id,
        created_by=actor_id,
    )
    db.add(cash_count)
    db.commit()
    db.refresh(cash_count)

    now = datetime.now(timezone.utc)

    event_bus.publish(DomainEvent(
        event_id=uuid.uuid4(),
        event_type="cash_count.recorded",
        occurred_at=now,
        company_id=company_id,
        idempotency_key=f"cash_count_recorded:{cash_count.cash_count_id}",
        actor={"type": "TENANT_USER", "id": str(actor_id)},
        payload={
            "cash_count_id": str(cash_count.cash_count_id),
            "resolution": resolution,
            "discrepancy": str(discrepancy),
        },
    ))

    if resolution == "ADJUSTED" and entry_id is not None:
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type="cash_count.adjustment_created",
            occurred_at=now,
            company_id=company_id,
            idempotency_key=f"cash_count_adjustment:{cash_count.cash_count_id}",
            actor={"type": "TENANT_USER", "id": str(actor_id)},
            payload={
                "cash_count_id": str(cash_count.cash_count_id),
                "entry_id": str(entry_id),
                "discrepancy": str(discrepancy),
            },
        ))

    return cash_count


def list_cash_counts(company_id: UUID, db: Session) -> list[CashCount]:
    return (
        db.query(CashCount)
        .filter(CashCount.company_id == company_id)
        .order_by(CashCount.created_at.desc())
        .all()
    )
