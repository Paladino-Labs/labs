"""PaymentsEngine — Sprint 9.

Ciclo de vida: PENDING → CONFIRMED → REFUNDED | FAILED | CANCELLED

ATOMICIDADE CRÍTICA em confirm():
  Os 5 passos (idempotency check, PaymentTransaction INSERT, payment UPDATE,
  FinancialCoreEngine, ProcessedIdempotencyKey INSERT) ocorrem na mesma
  transação de banco ou nenhum persiste.

  EventBus.publish("payment.confirmed") é chamado APÓS o commit — nunca
  dentro da transação.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.core.idempotency import is_processed, mark_processed
from app.infrastructure.db.models.deposit_policy import DepositPolicy
from app.infrastructure.db.models.payment import Payment
from app.infrastructure.db.models.payment_transaction import PaymentTransaction
from app.infrastructure.event_bus import DomainEvent, event_bus
from app.modules.financial_core import service as financial_core


class RefundReason(str, Enum):
    SERVICE_FAILURE = "SERVICE_FAILURE"
    REGISTRATION_ERROR = "REGISTRATION_ERROR"
    DEADLINE_POLICY = "DEADLINE_POLICY"
    OTHER = "OTHER"


_PAYMENT_METHOD_TO_FEE_SOURCE: dict[str, Optional[str]] = {
    "PIX": "ASAAS_PIX",
    "BOLETO": "ASAAS_PIX",
    "CARD_CREDIT": "ASAAS_CARD",
    "CARD_DEBIT": "ASAAS_CARD",
    "MAQUININHA": "MAQUININHA_CREDIT",
    "CASH": None,  # sem taxa de provider em pagamento em dinheiro
}

_CONSUMER = "payment_confirmed"


def _fee_source_for(payment_method: str) -> Optional[str]:
    return _PAYMENT_METHOD_TO_FEE_SOURCE.get(payment_method.upper(), "ASAAS_PIX")


def _get_payment(payment_id: UUID, company_id: UUID, db: Session) -> Payment:
    payment = (
        db.query(Payment)
        .filter(Payment.payment_id == payment_id, Payment.company_id == company_id)
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    return payment


# ── CRUD ──────────────────────────────────────────────────────────────────────

def create_payment(
    company_id: UUID,
    customer_id: Optional[UUID],
    gross_amount: Decimal,
    payment_method: str,
    provider: str,
    target_account_id: UUID,
    appointment_id: Optional[UUID] = None,
    payment_source_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> Payment:
    payment = Payment(
        company_id=company_id,
        customer_id=customer_id,
        appointment_id=appointment_id,
        gross_catalog_amount=gross_amount,
        discount_amount=Decimal("0"),
        net_charged_amount=gross_amount,
        payment_method=payment_method,
        payment_source_id=payment_source_id,
        provider=provider,
        target_account_id=target_account_id,
        status="PENDING",
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


def list_payments(company_id: UUID, db: Session) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(Payment.company_id == company_id)
        .order_by(Payment.created_at.desc())
        .all()
    )


def get_payment(payment_id: UUID, company_id: UUID, db: Session) -> Payment:
    return _get_payment(payment_id, company_id, db)


# ── FSM ───────────────────────────────────────────────────────────────────────

def confirm(
    payment_id: UUID,
    event_id: str,
    webhook_data: dict,
    company_id: UUID,
    db: Session,
) -> Payment:
    """Confirma pagamento com atomicidade total.

    Todos os 5 passos ocorrem na mesma transação ou nenhum persiste:
      1. Checar ProcessedIdempotencyKey — se já existe, retorna sem reprocessar.
      2. INSERT PaymentTransaction — IntegrityError = duplicata = retorna payment.
      3. UPDATE payments SET status=CONFIRMED, paid_at=now().
      4. FinancialCoreEngine.handle_payment_confirmed (Movements + Entries).
      5. INSERT ProcessedIdempotencyKey.
    COMMIT — só então EventBus.publish("payment.confirmed").
    """
    payment = _get_payment(payment_id, company_id, db)

    # Passo 1: idempotência via processed_idempotency_keys
    if is_processed(key=event_id, consumer=_CONSUMER, db=db):
        return payment

    amount = Decimal(str(webhook_data.get("value", str(payment.net_charged_amount))))
    provider_fee = Decimal(str(webhook_data.get("fee", str(payment.provider_fee))))

    try:
        # Passo 2: INSERT PaymentTransaction — UNIQUE(company_id, provider_transaction_id)
        txn = PaymentTransaction(
            payment_id=payment.payment_id,
            company_id=company_id,
            provider_transaction_id=event_id,
            amount=amount,
            status="CONFIRMED",
            raw_response=webhook_data,
        )
        db.add(txn)
        db.flush()

        # Passo 3: UPDATE payment
        payment.status = "CONFIRMED"
        payment.paid_at = datetime.now(timezone.utc)
        if provider_fee > Decimal("0"):
            payment.provider_fee = provider_fee
        db.flush()

        # Passo 4: FinancialCoreEngine — Movements + Entries nesta mesma tx
        fee_source = _fee_source_for(payment.payment_method)
        financial_core.handle_payment_confirmed(
            payment_id=payment.payment_id,
            gross_amount=payment.net_charged_amount,
            provider_fee=payment.provider_fee,
            target_account_id=payment.target_account_id,
            fee_source=fee_source,
            company_id=company_id,
            db=db,
        )

        # Passo 5: marcar idempotência (mesma transação)
        mark_processed(
            key=event_id,
            consumer=_CONSUMER,
            event_id=uuid.uuid4(),
            db=db,
            company_id=company_id,
            result_summary="payment_confirmed",
        )

        # COMMIT atômico dos 5 passos
        db.commit()

    except IntegrityError:
        # UNIQUE(company_id, provider_transaction_id) violado: duplicata de evento
        db.rollback()
        return (
            db.query(Payment)
            .filter(Payment.payment_id == payment_id, Payment.company_id == company_id)
            .first()
        )
    except Exception:
        db.rollback()
        raise

    db.refresh(payment)

    # Após commit: EventBus best-effort — falha não impacta o pagamento confirmado
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type="payment.confirmed",
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=f"payment.confirmed:{payment.payment_id}",
            actor={"type": "SYSTEM", "id": str(company_id)},
            payload={
                "payment_id": str(payment.payment_id),
                "customer_id": str(payment.customer_id) if payment.customer_id else None,
                "amount": str(payment.net_charged_amount),
                "company_id": str(company_id),
            },
        ))
    except Exception:
        pass

    return payment


def refund(
    payment_id: UUID,
    reason: RefundReason,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> Payment:
    """Estorna pagamento confirmado.

    Na mesma transação:
      Movement OUTFLOW + Entry ESTORNO via FinancialCoreEngine.
      record_sensitive_action com reason obrigatório.
    Após commit: EventBus.publish("payment.refunded") best-effort.
    """
    payment = _get_payment(payment_id, company_id, db)

    if payment.status != "CONFIRMED":
        raise HTTPException(
            status_code=422,
            detail=f"Pagamento deve estar CONFIRMED para estorno. Status atual: {payment.status}",
        )

    # Movement OUTFLOW + Entry ESTORNO (mesma transação)
    financial_core.handle_payment_refunded(
        payment_id=payment.payment_id,
        gross_amount=payment.net_charged_amount,
        target_account_id=payment.target_account_id,
        company_id=company_id,
        db=db,
    )

    payment.status = "REFUNDED"
    payment.refunded_at = datetime.now(timezone.utc)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="OWNER",
            action="refund_payment",
            resource_type="Payment",
            resource_id=payment.payment_id,
            company_id=company_id,
            reason=reason.value if isinstance(reason, RefundReason) else str(reason),
            amount=payment.net_charged_amount,
        ),
        db,
    )

    db.commit()
    db.refresh(payment)

    # Após commit: best-effort
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type="payment.refunded",
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=f"payment.refunded:{payment.payment_id}",
            actor={"type": "TENANT_USER", "id": str(actor_id)},
            payload={
                "payment_id": str(payment.payment_id),
                "reason": reason.value if isinstance(reason, RefundReason) else str(reason),
                "amount": str(payment.net_charged_amount),
            },
        ))
    except Exception:
        pass

    return payment


# ── DepositPolicy CRUD ────────────────────────────────────────────────────────

def list_deposit_policies(company_id: UUID, db: Session) -> list[DepositPolicy]:
    return (
        db.query(DepositPolicy)
        .filter(DepositPolicy.company_id == company_id)
        .order_by(DepositPolicy.created_at)
        .all()
    )


def create_deposit_policy(
    company_id: UUID,
    deposit_type: str,
    deposit_value: Decimal,
    service_id: Optional[UUID] = None,
    refundable_until_hours_before: int = 24,
    refund_on_tenant_fault: bool = True,
    retain_on_no_show: bool = True,
    commission_on_retained_deposit: bool = False,
    db: Optional[Session] = None,
) -> DepositPolicy:
    if deposit_type not in ("FIXED_AMOUNT", "PERCENTAGE"):
        raise HTTPException(
            status_code=422,
            detail="deposit_type deve ser FIXED_AMOUNT ou PERCENTAGE",
        )
    policy = DepositPolicy(
        company_id=company_id,
        service_id=service_id,
        deposit_type=deposit_type,
        deposit_value=deposit_value,
        refundable_until_hours_before=refundable_until_hours_before,
        refund_on_tenant_fault=refund_on_tenant_fault,
        retain_on_no_show=retain_on_no_show,
        commission_on_retained_deposit=commission_on_retained_deposit,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


def update_deposit_policy(
    policy_id: UUID,
    company_id: UUID,
    db: Session,
    **kwargs,
) -> DepositPolicy:
    policy = (
        db.query(DepositPolicy)
        .filter(DepositPolicy.policy_id == policy_id, DepositPolicy.company_id == company_id)
        .first()
    )
    if not policy:
        raise HTTPException(status_code=404, detail="Política de depósito não encontrada")

    allowed = {
        "deposit_type", "deposit_value", "refundable_until_hours_before",
        "refund_on_tenant_fault", "retain_on_no_show", "commission_on_retained_deposit",
    }
    for field, value in kwargs.items():
        if field in allowed and value is not None:
            setattr(policy, field, value)

    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return policy
