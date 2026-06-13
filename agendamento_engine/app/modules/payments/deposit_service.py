"""DepositService — orquestra o fluxo de sinal/depósito (Sprint 25).

Conecta primitivas que já existiam isoladas, SEM novas colunas de schema:
  - DepositPolicy (CRUD em payments/service.py)
  - Reservation SOFT/FIRME (agenda/reservation_service.py)
  - Payment (PENDING → CONFIRMED → REFUNDED)
  - FinancialCore (Movement INFLOW/OUTFLOW + Entry RECEITA/ESTORNO)

Invariantes do Estágio 0 (Contrato 3):
  1. Agendamento com DepositPolicy → Payment PENDING no momento da reserva.
  2. payment.confirmed → promove Reservation SOFT → FIRME.
  3. COMPLETED → saldo restante reconhecido como INFLOW + RECEITA.
  4. NO_SHOW → sinal retido se retain_on_no_show (default True); sem comissão
     sobre sinal retido salvo commission_on_retained_deposit (default False).
  5. Cancelamento dentro da janela → refund do sinal; fora → retido.

Todas as funções de leitura retornam None/no-op quando não há DepositPolicy
configurada para o tenant/serviço — fluxos sem sinal não são afetados.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models.deposit_policy import DepositPolicy
from app.infrastructure.db.models.payment import Payment
from app.infrastructure.db.models.reservation import Reservation

logger = logging.getLogger(__name__)


# ── Resolução de política ───────────────────────────────────────────────────

def resolve_deposit_policy(
    service_id: Optional[UUID],
    company_id: UUID,
    db: Session,
) -> Optional[DepositPolicy]:
    """Política específica do serviço tem prioridade sobre a global (service_id NULL)."""
    if service_id is not None:
        specific = (
            db.query(DepositPolicy)
            .filter(
                DepositPolicy.company_id == company_id,
                DepositPolicy.service_id == service_id,
            )
            .first()
        )
        if specific is not None:
            return specific
    return (
        db.query(DepositPolicy)
        .filter(
            DepositPolicy.company_id == company_id,
            DepositPolicy.service_id == None,  # noqa: E711 — SQLAlchemy IS NULL
        )
        .first()
    )


def compute_deposit_amount(policy: DepositPolicy, total_amount: Decimal) -> Decimal:
    """FIXED_AMOUNT → deposit_value; PERCENTAGE → total × value/100. Nunca > total."""
    total = Decimal(str(total_amount))
    if policy.deposit_type == "FIXED_AMOUNT":
        amount = Decimal(str(policy.deposit_value))
    elif policy.deposit_type == "PERCENTAGE":
        amount = total * (Decimal(str(policy.deposit_value)) / Decimal("100"))
    else:
        amount = Decimal("0")
    amount = min(amount, total)
    return amount.quantize(Decimal("0.01"))


def _first_service_id(appointment) -> Optional[UUID]:
    services = getattr(appointment, "services", None) or []
    for svc in services:
        if getattr(svc, "service_id", None) is not None:
            return svc.service_id
    return None


# ── 1. Criação do sinal na reserva ──────────────────────────────────────────

def create_deposit_payment(
    appointment,
    db: Session,
    payment_method: str = "CHAVE_PIX",
    target_account_id: Optional[UUID] = None,
) -> Optional[Payment]:
    """Cria Payment PENDING do sinal vinculado ao appointment.

    Retorna None quando não há DepositPolicy aplicável (fluxo sem sinal).
    O Payment é sempre provider=manual/PENDING — a confirmação segue o fluxo
    normal de payments (confirm/confirm_manual), que dispara payment.confirmed.
    """
    service_id = _first_service_id(appointment)
    policy = resolve_deposit_policy(service_id, appointment.company_id, db)
    if policy is None:
        return None

    deposit_amount = compute_deposit_amount(policy, appointment.total_amount)
    if deposit_amount <= 0:
        return None

    if target_account_id is None:
        from app.modules.payments.service import _resolve_target_account
        target_account_id = _resolve_target_account(appointment.company_id, db)

    payment = Payment(
        company_id=appointment.company_id,
        customer_id=appointment.client_id,
        appointment_id=appointment.id,
        gross_catalog_amount=deposit_amount,
        discount_amount=Decimal("0"),
        net_charged_amount=deposit_amount,
        provider_fee=Decimal("0"),
        payment_method=payment_method,
        provider="manual",
        target_account_id=target_account_id,
        status="PENDING",
    )
    db.add(payment)
    db.flush()
    return payment


# ── 2. Promoção SOFT → FIRME ao confirmar o sinal ───────────────────────────

def promote_reservation_for_appointment(
    appointment_id: UUID,
    company_id: UUID,
    db: Session,
) -> Optional[Reservation]:
    """Promove a Reservation SOFT ACTIVE do slot do appointment para FIRME.

    O Payment não referencia a Reservation diretamente (sem coluna); o vínculo
    é feito pelo slot (professional + start/end). No-op se não houver SOFT ativa.
    """
    from app.infrastructure.db.models.appointment import Appointment

    appt = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id, Appointment.company_id == company_id)
        .first()
    )
    if appt is None:
        return None

    soft = (
        db.query(Reservation)
        .filter(
            Reservation.company_id == company_id,
            Reservation.professional_id == appt.professional_id,
            Reservation.start_at == appt.start_at,
            Reservation.end_at == appt.end_at,
            Reservation.type == "SOFT",
            Reservation.status == "ACTIVE",
        )
        .first()
    )
    if soft is None:
        return None

    from app.modules.agenda import reservation_service
    return reservation_service.promote_to_firme(
        reservation_id=soft.reservation_id,
        appointment_id=appointment_id,
        company_id=company_id,
        db=db,
    )


# ── Helpers de pagamento confirmado ─────────────────────────────────────────

def _confirmed_payments(appointment, db: Session) -> list[Payment]:
    return (
        db.query(Payment)
        .filter(
            Payment.appointment_id == appointment.id,
            Payment.company_id == appointment.company_id,
            Payment.status == "CONFIRMED",
        )
        .all()
    )


# ── 3. Reconhecimento do saldo ao concluir ──────────────────────────────────

def recognize_balance_on_completion(appointment, db: Session) -> Optional[dict]:
    """Ao COMPLETED, reconhece o saldo restante (total − sinal confirmado).

    No-op quando não há pagamento parcial confirmado (fluxo de pagamento
    integral já reconheceu a receita no confirm — saldo 0).
    """
    confirmed = _confirmed_payments(appointment, db)
    if not confirmed:
        return None  # sem sinal confirmado → nada a reconhecer aqui

    paid = sum((Decimal(str(p.net_charged_amount)) for p in confirmed), Decimal("0"))
    total = Decimal(str(appointment.total_amount))
    balance = (total - paid).quantize(Decimal("0.01"))
    if balance <= 0:
        return None  # pagamento já cobre o total

    target_account_id = confirmed[0].target_account_id
    from app.modules.financial_core import service as financial_service
    result = financial_service.handle_deposit_balance_recognized(
        appointment_id=appointment.id,
        amount=balance,
        target_account_id=target_account_id,
        company_id=appointment.company_id,
        db=db,
    )
    db.commit()
    return {"balance": balance, **result}


# ── 4. Reembolso / retenção ─────────────────────────────────────────────────

def is_within_refund_window(
    start_at: datetime,
    now: datetime,
    refundable_until_hours_before: int,
) -> bool:
    """True se now é anterior ao limite (start_at − N horas) — refund permitido."""
    deadline = start_at - timedelta(hours=refundable_until_hours_before)
    return now <= deadline


def _refund_confirmed_deposits(appointment, db: Session) -> Decimal:
    """Estorna os pagamentos de sinal confirmados (Movement OUTFLOW + Entry ESTORNO)."""
    from app.modules.financial_core import service as financial_service

    refunded_total = Decimal("0")
    for p in _confirmed_payments(appointment, db):
        amount = Decimal(str(p.net_charged_amount))
        financial_service.handle_payment_refunded(
            payment_id=p.payment_id,
            gross_amount=amount,
            target_account_id=p.target_account_id,
            company_id=appointment.company_id,
            db=db,
        )
        p.status = "REFUNDED"
        p.refunded_at = datetime.now(timezone.utc)
        refunded_total += amount
    return refunded_total


def handle_cancellation_deposit(
    appointment,
    db: Session,
    now: Optional[datetime] = None,
) -> dict:
    """Cancelamento: refund dentro da janela; retenção fora dela.

    No-op (refunded=False, retained=False) quando não há DepositPolicy.
    """
    now = now or datetime.now(timezone.utc)
    service_id = _first_service_id(appointment)
    policy = resolve_deposit_policy(service_id, appointment.company_id, db)
    if policy is None:
        return {"refunded": False, "retained": False, "amount": Decimal("0")}

    within = is_within_refund_window(
        appointment.start_at, now, policy.refundable_until_hours_before
    )
    if within:
        amount = _refund_confirmed_deposits(appointment, db)
        db.commit()
        return {"refunded": True, "retained": False, "amount": amount}

    # Fora da janela → sinal retido (já reconhecido como receita no confirm)
    retained = sum(
        (Decimal(str(p.net_charged_amount)) for p in _confirmed_payments(appointment, db)),
        Decimal("0"),
    )
    return {"refunded": False, "retained": True, "amount": retained}


# ── 5. No-show ──────────────────────────────────────────────────────────────

def handle_no_show_deposit(appointment, db: Session) -> dict:
    """NO_SHOW: retém o sinal se retain_on_no_show (default True).

    Sinal retido NÃO gera comissão salvo commission_on_retained_deposit=True
    (default False). Se retain_on_no_show=False, estorna o sinal.
    """
    service_id = _first_service_id(appointment)
    policy = resolve_deposit_policy(service_id, appointment.company_id, db)
    if policy is None:
        return {"retained": False, "commission": False, "amount": Decimal("0")}

    confirmed_total = sum(
        (Decimal(str(p.net_charged_amount)) for p in _confirmed_payments(appointment, db)),
        Decimal("0"),
    )

    if not policy.retain_on_no_show:
        amount = _refund_confirmed_deposits(appointment, db)
        db.commit()
        return {"retained": False, "commission": False, "amount": amount}

    # Retido: receita já reconhecida no confirm; nada a estornar.
    return {
        "retained": True,
        "commission": bool(policy.commission_on_retained_deposit),
        "amount": confirmed_total,
    }
