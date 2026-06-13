"""Contrato 3 — Fluxo DEPOSIT ponta a ponta (Sprint 25 — wiring).

Exercita app/modules/payments/deposit_service.py, que conecta DepositPolicy +
Reservation SOFT/FIRME + Payment + FinancialCore.

NOTA DE CONTRATO: o enunciado fala em "SOFT_RESERVATION → CONFIRMED (firme)".
No Estágio 0 isso é a promoção da **Reservation** SOFT→FIRME (domínio separado
do status do Appointment), não um estado da FSM de Appointment.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.infrastructure.db.models.account import Account
from app.infrastructure.db.models.deposit_policy import DepositPolicy
from app.infrastructure.db.models.entry import Entry
from app.infrastructure.db.models.payment import Payment
from app.infrastructure.db.models.reservation import Reservation
from app.modules.payments import deposit_service


def _policy(company_id, deposit_type="FIXED_AMOUNT", value=Decimal("30"),
            service_id=None, retain_on_no_show=True,
            commission_on_retained=False, refundable_hours=24):
    return DepositPolicy(
        policy_id=uuid.uuid4(), company_id=company_id, service_id=service_id,
        deposit_type=deposit_type, deposit_value=value,
        refundable_until_hours_before=refundable_hours,
        refund_on_tenant_fault=True,
        retain_on_no_show=retain_on_no_show,
        commission_on_retained_deposit=commission_on_retained,
    )


def _appt(company_id, total=Decimal("100"), start_at=None):
    now = datetime.now(timezone.utc)
    start_at = start_at or (now + timedelta(days=2))
    return SimpleNamespace(
        id=uuid.uuid4(), company_id=company_id, client_id=uuid.uuid4(),
        professional_id=uuid.uuid4(), start_at=start_at,
        end_at=start_at + timedelta(hours=1), total_amount=total,
        services=[SimpleNamespace(service_id=uuid.uuid4(), price_snapshot=total)],
    )


def _account(db, company_id):
    acc = Account(company_id=company_id, name="CAIXA", type="CAIXA",
                  currency="BRL", is_default_inflow=True)
    db.add(acc)
    return acc


def _confirmed_payment(db, appt, amount, account_id):
    p = Payment(company_id=appt.company_id, customer_id=appt.client_id,
                appointment_id=appt.id, gross_catalog_amount=amount,
                discount_amount=Decimal("0"), net_charged_amount=amount,
                provider_fee=Decimal("0"), payment_method="CHAVE_PIX",
                provider="manual", target_account_id=account_id, status="CONFIRMED")
    db.add(p)
    return p


class TestDepositPolicy:
    def test_compute_fixed_amount(self):
        p = _policy(uuid.uuid4(), "FIXED_AMOUNT", Decimal("30"))
        assert deposit_service.compute_deposit_amount(p, Decimal("100")) == Decimal("30.00")

    def test_compute_percentage(self):
        p = _policy(uuid.uuid4(), "PERCENTAGE", Decimal("20"))
        assert deposit_service.compute_deposit_amount(p, Decimal("100")) == Decimal("20.00")

    def test_specific_policy_over_global(self, db):
        cid, svc = uuid.uuid4(), uuid.uuid4()
        db.add(_policy(cid, value=Decimal("10")))                      # global
        db.add(_policy(cid, value=Decimal("50"), service_id=svc))      # específica
        resolved = deposit_service.resolve_deposit_policy(svc, cid, db)
        assert resolved.deposit_value == Decimal("50")


class TestDepositFlow:
    def test_deposit_creates_pending_payment(self, db):
        cid = uuid.uuid4()
        _account(db, cid)
        db.add(_policy(cid, "FIXED_AMOUNT", Decimal("30")))
        appt = _appt(cid)
        payment = deposit_service.create_deposit_payment(appt, db)
        assert payment is not None
        assert payment.status == "PENDING"
        assert payment.net_charged_amount == Decimal("30.00")
        assert payment.appointment_id == appt.id

    def test_no_policy_no_deposit(self, db):
        cid = uuid.uuid4()
        _account(db, cid)
        assert deposit_service.create_deposit_payment(_appt(cid), db) is None

    def test_payment_confirmation_promotes_soft_to_firme(self, db):
        from app.infrastructure.db.models.appointment import Appointment
        cid = uuid.uuid4()
        appt = _appt(cid)
        db.add(Appointment(id=appt.id, company_id=cid, client_id=appt.client_id,
                           professional_id=appt.professional_id,
                           start_at=appt.start_at, end_at=appt.end_at,
                           status="SCHEDULED"))
        soft = Reservation(reservation_id=uuid.uuid4(), company_id=cid,
                           professional_id=appt.professional_id,
                           start_at=appt.start_at, end_at=appt.end_at,
                           type="SOFT", status="ACTIVE")
        db.add(soft)
        firme = deposit_service.promote_reservation_for_appointment(appt.id, cid, db)
        assert firme is not None
        assert firme.type == "FIRME"
        assert firme.appointment_id == appt.id
        assert soft.status == "PROMOTED"

    def test_completed_releases_balance_as_revenue(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        appt = _appt(cid, total=Decimal("100"))
        _confirmed_payment(db, appt, Decimal("30"), acc.account_id)  # sinal
        result = deposit_service.recognize_balance_on_completion(appt, db)
        assert result["balance"] == Decimal("70.00")
        entries = [e for e in db.store_for(Entry) if e.type == "RECEITA"]
        assert any(e.amount == Decimal("70.00") for e in entries)

    def test_completed_no_deposit_is_noop(self, db):
        """Sem pagamento parcial confirmado → nada a reconhecer."""
        cid = uuid.uuid4()
        assert deposit_service.recognize_balance_on_completion(_appt(cid), db) is None

    def test_no_show_retains_deposit(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        db.add(_policy(cid, retain_on_no_show=True))
        appt = _appt(cid)
        p = _confirmed_payment(db, appt, Decimal("30"), acc.account_id)
        result = deposit_service.handle_no_show_deposit(appt, db)
        assert result["retained"] is True
        assert result["amount"] == Decimal("30")
        assert p.status == "CONFIRMED"  # sinal não devolvido

    def test_no_show_no_retain_refunds(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        db.add(_policy(cid, retain_on_no_show=False))
        appt = _appt(cid)
        p = _confirmed_payment(db, appt, Decimal("30"), acc.account_id)
        result = deposit_service.handle_no_show_deposit(appt, db)
        assert result["retained"] is False
        assert p.status == "REFUNDED"

    def test_cancellation_inside_window_refunds(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        db.add(_policy(cid, refundable_hours=24))
        appt = _appt(cid, start_at=datetime.now(timezone.utc) + timedelta(hours=48))
        p = _confirmed_payment(db, appt, Decimal("30"), acc.account_id)
        result = deposit_service.handle_cancellation_deposit(appt, db)
        assert result["refunded"] is True
        assert p.status == "REFUNDED"
        assert any(e.type == "ESTORNO" for e in db.store_for(Entry))

    def test_cancellation_outside_window_retains(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        db.add(_policy(cid, refundable_hours=24))
        appt = _appt(cid, start_at=datetime.now(timezone.utc) + timedelta(hours=1))
        p = _confirmed_payment(db, appt, Decimal("30"), acc.account_id)
        result = deposit_service.handle_cancellation_deposit(appt, db)
        assert result["retained"] is True
        assert p.status == "CONFIRMED"

    def test_commission_on_retained_deposit_default_false(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        db.add(_policy(cid, retain_on_no_show=True, commission_on_retained=False))
        appt = _appt(cid)
        _confirmed_payment(db, appt, Decimal("30"), acc.account_id)
        result = deposit_service.handle_no_show_deposit(appt, db)
        assert result["commission"] is False
