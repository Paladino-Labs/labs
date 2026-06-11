"""PayablesService — Sprint 17.

Lifecycle: OPEN → PARTIALLY_PAID → PAID | CANCELLED

Financial-1: criar Payable não cria Entry (receber ≠ reconhecer custo);
pay_installment cria Movement OUTFLOW sem Entry (origem stock_purchase —
o custo é reconhecido pelos movimentos de estoque).
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.infrastructure.db.models.payable import Payable, PayableInstallment
from app.modules.financial_core.service import handle_payable_installment_paid

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_payable_or_404(payable_id: UUID, company_id: UUID, db: Session) -> Payable:
    payable = (
        db.query(Payable)
        .filter(Payable.id == payable_id, Payable.company_id == company_id)
        .first()
    )
    if not payable:
        raise HTTPException(status_code=404, detail="Conta a pagar não encontrada")
    return payable


def _publish_event(event_type: str, idempotency_key: str, company_id: UUID, payload: dict) -> None:
    """Publica evento no EventBus — best-effort, nunca propaga exceção."""
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": None},
            payload=payload,
        ))
    except Exception:
        logger.exception("payables: falha ao publicar %s", event_type)


# ── API pública ───────────────────────────────────────────────────────────────

def create_payable(
    company_id: UUID,
    description: str,
    total_amount: Decimal,
    source_type: str,
    created_by: UUID,
    db: Session,
    supplier_id: Optional[UUID] = None,
    source_id: Optional[UUID] = None,
    closing_method: str = "CASH_AT_CREATION",
    installments: Optional[List[dict]] = None,
    due_date: Optional[date] = None,
    commit: bool = True,
) -> Payable:
    """Cria Payable OPEN + installments. SEM Entry (Financial-1).

    CASH_AT_CREATION → 1 installment com o valor total.
    INSTALLMENTS → installments obrigatório ([{amount, due_date}]),
    soma deve fechar com total_amount.

    commit=False permite composição na transação do receive_order.
    """
    total_amount = Decimal(str(total_amount))
    if total_amount <= 0:
        raise HTTPException(status_code=422, detail="total_amount deve ser > 0")
    if closing_method not in ("CASH_AT_CREATION", "INSTALLMENTS"):
        raise HTTPException(status_code=422, detail=f"closing_method inválido: {closing_method}")

    if closing_method == "INSTALLMENTS":
        if not installments:
            raise HTTPException(
                status_code=422,
                detail="installments é obrigatório quando closing_method=INSTALLMENTS",
            )
        installments_sum = sum(Decimal(str(i["amount"])) for i in installments)
        if installments_sum != total_amount:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Soma das parcelas ({installments_sum}) difere do "
                    f"total_amount ({total_amount})"
                ),
            )
        plan = installments
        payable_due_date = due_date or max(
            (i["due_date"] for i in installments if i.get("due_date")), default=None
        )
    else:
        plan = [{"amount": total_amount, "due_date": due_date or datetime.now(timezone.utc).date()}]
        payable_due_date = due_date or datetime.now(timezone.utc).date()

    payable = Payable(
        id=uuid.uuid4(),
        company_id=company_id,
        supplier_id=supplier_id,
        description=description,
        total_amount=total_amount,
        paid_amount=Decimal("0"),
        status="OPEN",
        due_date=payable_due_date,
        closing_method=closing_method,
        source_type=source_type,
        source_id=source_id,
        created_by=created_by,
    )
    db.add(payable)
    db.flush()

    for n, inst in enumerate(plan, start=1):
        db.add(PayableInstallment(
            id=uuid.uuid4(),
            payable_id=payable.id,
            company_id=company_id,
            amount=Decimal(str(inst["amount"])),
            due_date=inst.get("due_date"),
            installment_number=n,
            status="OPEN",
        ))
    db.flush()

    if commit:
        db.commit()
        db.refresh(payable)

    return payable


def pay_installment(
    payable_id: UUID,
    installment_id: UUID,
    company_id: UUID,
    db: Session,
    payment_id: Optional[UUID] = None,
    account_id: Optional[UUID] = None,
) -> Payable:
    """Paga uma parcela — atômico (um único commit):
      1. installment → PAID
      2. Movement OUTFLOW sem Entry (Financial-1 — origem stock_purchase)
      3. payable.paid_amount atualizado
      4. paid_amount >= total_amount → PAID; senão → PARTIALLY_PAID
    """
    payable = _get_payable_or_404(payable_id, company_id, db)

    if payable.status not in ("OPEN", "PARTIALLY_PAID"):
        raise HTTPException(
            status_code=422,
            detail=f"Payable não pode receber pagamento (status={payable.status})",
        )

    installment = (
        db.query(PayableInstallment)
        .filter(
            PayableInstallment.id == installment_id,
            PayableInstallment.payable_id == payable_id,
            PayableInstallment.company_id == company_id,
        )
        .first()
    )
    if not installment:
        raise HTTPException(status_code=404, detail="Parcela não encontrada")
    if installment.status == "PAID":
        raise HTTPException(status_code=422, detail="Parcela já está paga")

    now = datetime.now(timezone.utc)
    amount = Decimal(str(installment.amount))

    # Movement OUTFLOW sem Entry — falha aqui aborta tudo (nada commitado)
    handle_payable_installment_paid(
        installment_id=installment.id,
        amount=amount,
        company_id=company_id,
        db=db,
        account_id=account_id,
    )

    installment.status = "PAID"
    installment.paid_at = now
    installment.payment_id = payment_id

    payable.paid_amount = Decimal(str(payable.paid_amount or 0)) + amount
    fully_paid = payable.paid_amount >= Decimal(str(payable.total_amount))
    payable.status = "PAID" if fully_paid else "PARTIALLY_PAID"
    payable.updated_at = now

    db.commit()
    db.refresh(payable)

    event_type = "payable.paid" if fully_paid else "payable.installment_paid"
    _publish_event(
        event_type=event_type,
        idempotency_key=f"{event_type}:{installment.id}",
        company_id=company_id,
        payload={
            "payable_id": str(payable.id),
            "installment_id": str(installment.id),
            "company_id": str(company_id),
            "amount": str(amount),
            "paid_amount": str(payable.paid_amount),
            "status": payable.status,
        },
    )

    return payable


def cancel_payable(
    payable_id: UUID,
    company_id: UUID,
    reason: str,
    db: Session,
    actor_id: Optional[UUID] = None,
    actor_role: str = "OWNER",
) -> Payable:
    """OPEN → CANCELLED direto; PARTIALLY_PAID exige reason + audit;
    PAID não pode ser cancelado."""
    payable = _get_payable_or_404(payable_id, company_id, db)

    if payable.status == "PAID":
        raise HTTPException(status_code=422, detail="Payable PAID não pode ser cancelado")
    if payable.status == "CANCELLED":
        raise HTTPException(status_code=422, detail="Payable já está cancelado")

    if payable.status == "PARTIALLY_PAID":
        if not reason or not reason.strip():
            raise HTTPException(
                status_code=422,
                detail="reason é obrigatório para cancelar Payable PARTIALLY_PAID",
            )
        record_sensitive_action(
            SensitiveAuditContext(
                actor_id=actor_id,
                actor_role=actor_role,
                action="cancel_payable_partially_paid",
                resource_type="Payable",
                resource_id=payable.id,
                company_id=company_id,
                reason=reason,
                amount=Decimal(str(payable.paid_amount or 0)),
                after_snapshot={
                    "status": "CANCELLED",
                    "paid_amount": str(payable.paid_amount),
                    "total_amount": str(payable.total_amount),
                },
            ),
            db,
        )

    payable.status = "CANCELLED"
    payable.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(payable)

    _publish_event(
        event_type="payable.cancelled",
        idempotency_key=f"payable.cancelled:{payable.id}",
        company_id=company_id,
        payload={
            "payable_id": str(payable.id),
            "company_id": str(company_id),
            "reason": reason,
        },
    )

    return payable


def list_payables(
    company_id: UUID,
    db: Session,
    status: Optional[str] = None,
    supplier_id: Optional[UUID] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
) -> List[Payable]:
    q = db.query(Payable).filter(Payable.company_id == company_id)
    if status:
        q = q.filter(Payable.status == status)
    if supplier_id:
        q = q.filter(Payable.supplier_id == supplier_id)
    if due_date_from:
        q = q.filter(Payable.due_date >= due_date_from)
    if due_date_to:
        q = q.filter(Payable.due_date <= due_date_to)
    return q.order_by(Payable.due_date.desc()).all()


def get_payable(payable_id: UUID, company_id: UUID, db: Session) -> Payable:
    return _get_payable_or_404(payable_id, company_id, db)


def list_installments(payable_id: UUID, company_id: UUID, db: Session) -> List[PayableInstallment]:
    return (
        db.query(PayableInstallment)
        .filter(
            PayableInstallment.payable_id == payable_id,
            PayableInstallment.company_id == company_id,
        )
        .order_by(PayableInstallment.installment_number)
        .all()
    )
