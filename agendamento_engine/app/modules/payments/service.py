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

import logging
import re
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
from app.infrastructure.db.models.tenant_fee_routing_policy import TenantFeeRoutingPolicy
from app.infrastructure.event_bus import DomainEvent, event_bus
from app.modules.financial_core import service as financial_core
from app.modules.payments.provider_factory import get_payment_provider

logger = logging.getLogger(__name__)


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
    "MAQUININHA_CREDIT": "MAQUININHA_CREDIT",
    "MAQUININHA_DEBIT": "MAQUININHA_DEBIT",
    "MAQUININHA_PIX": "MAQUININHA_PIX",
    "CASH": None,  # sem taxa de provider em pagamento em dinheiro
}

# Métodos de maquininha que têm política de taxa MDR configurável.
_MAQUININHA_METHODS = frozenset({"MAQUININHA", "MAQUININHA_CREDIT", "MAQUININHA_DEBIT", "MAQUININHA_PIX"})

# Labels legíveis para mensagens de aviso exibidas ao operador.
_FEE_SOURCE_LABELS: dict[str, str] = {
    "MAQUININHA_CREDIT": "crédito na maquininha",
    "MAQUININHA_DEBIT": "débito na maquininha",
    "MAQUININHA_PIX": "PIX na maquininha",
}

_CONSUMER = "payment_confirmed"


def _fee_source_for(payment_method: str) -> Optional[str]:
    return _PAYMENT_METHOD_TO_FEE_SOURCE.get(payment_method.upper(), "ASAAS_PIX")


def _fee_warning_message(fee_source: str) -> str:
    label = _FEE_SOURCE_LABELS.get(fee_source, fee_source)
    return (
        f"Nenhuma taxa configurada para {label}. "
        "Configure em Configurações → Financeiro → Taxas."
    )


def _get_payment(payment_id: UUID, company_id: UUID, db: Session) -> Payment:
    payment = (
        db.query(Payment)
        .filter(Payment.payment_id == payment_id, Payment.company_id == company_id)
        .first()
    )
    if not payment:
        raise HTTPException(status_code=404, detail="Pagamento não encontrado")
    return payment


# ── Helpers de validação ──────────────────────────────────────────────────────

def _clean_cpf_cnpj(value: str) -> str:
    """Remove formatação e retorna apenas os dígitos."""
    return re.sub(r"\D", "", value)


def _validate_cpf(digits: str) -> bool:
    """Valida CPF (11 dígitos) pelos dígitos verificadores."""
    if len(digits) != 11 or len(set(digits)) == 1:
        return False
    # Primeiro dígito verificador
    s = sum(int(d) * (10 - i) for i, d in enumerate(digits[:9]))
    r = (s * 10 % 11) % 10
    if r != int(digits[9]):
        return False
    # Segundo dígito verificador
    s = sum(int(d) * (11 - i) for i, d in enumerate(digits[:10]))
    r = (s * 10 % 11) % 10
    return r == int(digits[10])


def _validate_cnpj(digits: str) -> bool:
    """Valida CNPJ (14 dígitos) pelos dígitos verificadores."""
    if len(digits) != 14 or len(set(digits)) == 1:
        return False
    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    s = sum(int(d) * w for d, w in zip(digits[:12], w1))
    r = 0 if s % 11 < 2 else 11 - s % 11
    if r != int(digits[12]):
        return False
    s = sum(int(d) * w for d, w in zip(digits[:13], w2))
    r = 0 if s % 11 < 2 else 11 - s % 11
    return r == int(digits[13])


def validate_and_clean_cpf_cnpj(raw: str) -> str:
    """Limpa e valida CPF ou CNPJ. Levanta HTTP 422 se inválido.

    Retorna os dígitos limpos prontos para envio ao Asaas.
    """
    digits = _clean_cpf_cnpj(raw)
    if len(digits) == 11:
        if not _validate_cpf(digits):
            raise HTTPException(status_code=422, detail="CPF inválido.")
    elif len(digits) == 14:
        if not _validate_cnpj(digits):
            raise HTTPException(status_code=422, detail="CNPJ inválido.")
    else:
        raise HTTPException(
            status_code=422,
            detail="CPF/CNPJ inválido: deve ter 11 dígitos (CPF) ou 14 dígitos (CNPJ).",
        )
    return digits


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
    customer_cpf_cnpj: Optional[str] = None,
    due_date=None,          # date | None — padrão: hoje
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
    db.flush()

    # Cria cobrança no provider antes do commit; falha reverte a transação inteira.
    # CASH e provider=manual não passam pelo provider externo.
    _is_cash_or_manual = payment_method.upper() == "CASH" or provider.lower() == "manual"
    if not _is_cash_or_manual:
        prov = get_payment_provider(company_id=company_id, db=db)

        # Resolve o Asaas customer ID (cus_...) para este cliente.
        # Lazy registration: cria no Asaas na primeira cobrança e persiste o ID.
        from datetime import date as _date
        # Valida e limpa CPF/CNPJ antes de qualquer chamada ao Asaas.
        clean_cpf_cnpj: str | None = None
        if customer_cpf_cnpj:
            clean_cpf_cnpj = validate_and_clean_cpf_cnpj(customer_cpf_cnpj)

        asaas_customer_id: str | None = None
        if customer_id:
            from app.infrastructure.db.models.customer import Customer
            cust = db.query(Customer).filter(Customer.id == customer_id).first()
            if cust:
                from app.modules.payments.providers.asaas import AsaasProvider
                if isinstance(prov, AsaasProvider):
                    if not cust.asaas_customer_id:
                        cust.asaas_customer_id = prov.ensure_customer(
                            name=cust.name,
                            email=cust.email,
                            external_reference=str(customer_id),
                            cpf_cnpj=clean_cpf_cnpj,
                        )
                        db.flush()
                    elif clean_cpf_cnpj:
                        # Customer Asaas já existe mas CPF/CNPJ não foi informado antes;
                        # atualiza via PUT para habilitar PIX/BOLETO.
                        prov.update_customer(
                            asaas_id=cust.asaas_customer_id,
                            cpf_cnpj=clean_cpf_cnpj,
                        )
                asaas_customer_id = cust.asaas_customer_id

        _due_date = (due_date or _date.today()).strftime("%Y-%m-%d")
        charge = prov.create_charge(
            amount=gross_amount,
            customer={"external_id": asaas_customer_id} if asaas_customer_id else {},
            payment_method=payment_method.upper(),
            dueDate=_due_date,
        )
        payment.external_charge_id = charge["id"]

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

    # Payload Asaas real: {"event": "...", "payment": {"value": 100, "fee": 3, ...}}
    # Fallback legado: {"value": 100, "fee": 3} no nível raiz.
    _pd = webhook_data.get("payment")
    _pd = _pd if isinstance(_pd, dict) else {}
    amount = Decimal(str(
        _pd["value"] if "value" in _pd else webhook_data.get("value", str(payment.net_charged_amount))
    ))
    provider_fee = Decimal(str(
        _pd["fee"] if "fee" in _pd else webhook_data.get("fee", str(payment.provider_fee))
    ))

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


def _calc_manual_fee(
    payment: Payment, db: Session, payment_submethod: Optional[str] = None
) -> tuple[Decimal, Optional[str]]:
    """Calcula taxa MDR para pagamento manual. Retorna (fee, warning_fee_source).

    warning_fee_source não-None indica que a taxa não está configurada:
      - Política não encontrada ou inativa.
      - Política ativa mas fee_percentage IS NULL (não configurado pelo operador).

    CASH → (Decimal("0"), None) — sem consulta ao banco.
    MAQUININHA (genérico) + payment_submethod="DEBIT" → consulta MAQUININHA_DEBIT.
    MAQUININHA (genérico) + payment_submethod="CREDIT" ou None → consulta MAQUININHA_CREDIT.
    MAQUININHA_CREDIT → consulta política MAQUININHA_CREDIT.
    MAQUININHA_DEBIT → consulta política MAQUININHA_DEBIT.
    MAQUININHA_PIX   → consulta política MAQUININHA_PIX.
    Outros métodos   → (Decimal("0"), None) sem consulta.
    """
    method = payment.payment_method.upper()

    if method == "CASH":
        return Decimal("0"), None

    if method not in _MAQUININHA_METHODS:
        return Decimal("0"), None

    fee_source = _PAYMENT_METHOD_TO_FEE_SOURCE[method]
    # Quando method é "MAQUININHA" (genérico), payment_submethod determina crédito vs débito
    if method == "MAQUININHA" and payment_submethod:
        submethod = payment_submethod.upper()
        if submethod == "DEBIT":
            fee_source = "MAQUININHA_DEBIT"
        elif submethod == "CREDIT":
            fee_source = "MAQUININHA_CREDIT"

    policy = (
        db.query(TenantFeeRoutingPolicy)
        .filter(
            TenantFeeRoutingPolicy.company_id == payment.company_id,
            TenantFeeRoutingPolicy.fee_source == fee_source,
        )
        .first()
    )

    if not policy or not policy.is_active:
        logger.warning(
            "manual_fee_policy_not_found fee_source=%s company_id=%s",
            fee_source,
            payment.company_id,
        )
        return Decimal("0"), fee_source

    if policy.fee_percentage is None:
        return Decimal("0"), fee_source

    gross = Decimal(str(payment.gross_catalog_amount))
    fee_pct = Decimal(str(policy.fee_percentage))
    fee = round(gross * fee_pct / Decimal("100"), 2)
    fee_flat = Decimal(str(policy.fee_flat)) if policy.fee_flat is not None else Decimal("0")
    if fee_flat > Decimal("0"):
        fee += fee_flat
    return fee, None


def confirm_manual(
    payment_id: UUID,
    company_id: UUID,
    db: Session,
    payment_submethod: Optional[str] = None,
) -> tuple[Payment, Optional[dict]]:
    """Confirma pagamento CASH ou provider=manual de forma síncrona e idempotente.

    Wrapper de confirm() com event_id sintético determinístico:
        event_id = f"manual-{payment.payment_id}"

    Para MAQUININHA/MAQUININHA_PIX (provider=manual): calcula taxa MDR via
    TenantFeeRoutingPolicy. Quando taxa não está configurada (fee_percentage=NULL),
    confirma normalmente e retorna fee_warning no segundo elemento da tupla.
    Para CASH: fee sempre zero, sem warning.

    Retorna:
        (Payment, None)       — confirmado, sem aviso.
        (Payment, dict)       — confirmado, mas taxa não configurada (ver dict).

    Idempotência: re-submit em payment já CONFIRMED retorna (payment, None).
    """
    payment = _get_payment(payment_id, company_id, db)

    is_cash_or_manual = (
        payment.payment_method.upper() == "CASH"
        or payment.provider == "manual"
    )
    if not is_cash_or_manual:
        raise HTTPException(
            status_code=422,
            detail=(
                f"confirm-manual só é permitido para pagamentos CASH ou provider=manual. "
                f"payment_method={payment.payment_method}, provider={payment.provider}"
            ),
        )

    event_id = f"manual-{payment.payment_id}"

    # Status != PENDING: só é permitido se já foi processado (idempotência)
    if payment.status != "PENDING":
        if is_processed(key=event_id, consumer=_CONSUMER, db=db):
            return payment, None
        raise HTTPException(
            status_code=422,
            detail=f"Pagamento deve estar PENDING para confirmação manual. Status atual: {payment.status}",
        )

    fee, warning_fee_source = _calc_manual_fee(payment, db, payment_submethod=payment_submethod)

    fee_warning: Optional[dict] = None
    if warning_fee_source:
        fee_warning = {
            "code": "fee_not_configured",
            "fee_source": warning_fee_source,
            "fee_applied": float(fee),
            "message": _fee_warning_message(warning_fee_source),
        }

    webhook_data = {
        "value": str(payment.net_charged_amount),
        "fee": str(fee),
    }
    confirmed = confirm(
        payment_id=payment_id,
        event_id=event_id,
        webhook_data=webhook_data,
        company_id=company_id,
        db=db,
    )
    return confirmed, fee_warning


def refund(
    payment_id: UUID,
    reason: RefundReason,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> Payment:
    """Estorna pagamento confirmado.

    Ordem garantida:
      1. provider.refund() para pagamentos não-manual com external_charge_id.
         Se falhar: exceção propagada, banco não alterado.
      2. FinancialCoreEngine.handle_payment_refunded (Movement OUTFLOW + Entry ESTORNO).
      3. payment.status = REFUNDED, record_sensitive_action, commit.
    Após commit: EventBus.publish("payment.refunded") best-effort.

    Pagamentos CASH/manual (provider="manual"): sem chamada ao provider.
    """
    payment = _get_payment(payment_id, company_id, db)

    if payment.status != "CONFIRMED":
        raise HTTPException(
            status_code=422,
            detail=f"Pagamento deve estar CONFIRMED para estorno. Status atual: {payment.status}",
        )

    _is_manual = payment.provider == "manual"
    if not _is_manual and payment.external_charge_id:
        if payment.provider == "pagseguro":
            logger.warning(
                "pagseguro_refund_blocked",
                extra={
                    "payment_id": str(payment.payment_id),
                    "reason": "PagSeguro refund endpoint not confirmed — manual action required in PagSeguro dashboard",
                },
            )
            raise HTTPException(
                status_code=422,
                detail=(
                    "Estorno via PagSeguro não disponível — endpoint não confirmado. "
                    "Realize o estorno manualmente no painel PagSeguro e registre via PATCH /payments/{id}/status."
                ),
            )
        prov = get_payment_provider(company_id=company_id, db=db)
        prov.refund(
            payment.external_charge_id,
            reason.value if isinstance(reason, RefundReason) else str(reason),
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
