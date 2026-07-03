"""
Portal Camada 2 — companies, coupons, payments, detalhe de agendamento,
cancelar/remarcar autenticado e checkout com JWT portal opcional.

FakeDB in-memory (padrão Sprint D, estendido com or_) — sem PostgreSQL real.
NÃO importa app.main (contaminação de ordenação de test_sprint2_rbac).

Casos:
  1. GET /portal/companies retorna empresas da identity com slug
  2. GET /portal/coupons: nominais + genéricos, exclui expirados
  3. GET /portal/payments: paginação, só da identity
  4. GET /portal/appointments/{id}: detalhe com endereço; 404 se não é da identity
  5. POST /cancel: SCHEDULED cancela; não-SCHEDULED → 422; posse errada → 404;
     deposit_retained presente na resposta
  6. POST /reschedule: remarca; conflito → 422; não-SCHEDULED → 422; posse → 404
  7. Checkout autenticado: JWT portal cria/reusa customer da identity, ignora
     phone do body; sem token exige name+phone; token inválido → 401
  8. Checkout autenticado NÃO chama validate_user_phone_input
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.deps import get_current_portal_identity_optional
from app.infrastructure.db.models import (
    Appointment,
    Company,
    CompanyProfile,
    Coupon,
    Customer,
    PaladinoIdentity,
    Payment,
    Promotion,
)
from app.modules.portal import router as portal_router, service as portal_service

_NOW = datetime.now(timezone.utc)


# ─── FakeDB (padrão Sprint D + suporte a or_) ─────────────────────────────────

def _criterion_matches(obj, c) -> bool:
    # or_(...) → BooleanClauseList com .clauses
    clauses = getattr(c, "clauses", None)
    if clauses is not None:
        op_name = getattr(getattr(c, "operator", None), "__name__", "")
        results = [_criterion_matches(obj, sub) for sub in clauses]
        return all(results) if op_name == "and_" else any(results)

    key = c.left.key
    actual = getattr(obj, key, None)
    right = c.right
    op_name = getattr(c.operator, "__name__", "")

    if op_name == "in_op":
        values = getattr(right, "value", None) or []
        return actual in values

    right_cls = right.__class__.__name__
    if right_cls == "True_":
        val = True
    elif right_cls == "False_":
        val = False
    elif right_cls == "Null":
        val = None
    else:
        val = getattr(right, "value", None)

    if op_name in ("is_", "is_op"):
        return actual is val
    if op_name in ("ne", "is_not", "is_not_op"):
        return actual != val
    if op_name == "ge":
        return actual is not None and actual >= val
    if op_name == "gt":
        return actual is not None and actual > val
    if op_name == "le":
        return actual is not None and actual <= val
    if op_name == "lt":
        return actual is not None and actual < val
    return actual == val


class FakeQuery:
    def __init__(self, items):
        self.items = list(items)

    def filter(self, *criteria):
        return FakeQuery(
            [i for i in self.items if all(_criterion_matches(i, c) for c in criteria)]
        )

    def order_by(self, *args, **kwargs):
        return self

    def offset(self, n):
        return FakeQuery(self.items[n:])

    def limit(self, n):
        return FakeQuery(self.items[:n])

    def count(self):
        return len(self.items)

    def first(self):
        return self.items[0] if self.items else None

    def all(self):
        return list(self.items)


class FakeDB:
    def __init__(self):
        self.stores = {}
        self.commits = 0

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model):
        return FakeQuery(self._store(model))

    def add(self, obj):
        self._store(type(obj)).append(obj)

    def commit(self):
        self.commits += 1

    def flush(self):
        pass

    def refresh(self, obj):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_identity(db=None):
    identity = SimpleNamespace(
        id=uuid.uuid4(),
        name="Cliente Portal",
        phone_e164="+5562988887777",
        phone_national_normalized="62988887777",
        email=None,
    )
    if db is not None:
        db._store(PaladinoIdentity).append(identity)
    return identity


def _make_customer(db, identity, company_id=None, active=True):
    customer = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        name="Cliente Teste",
        phone="5562988887777",
        identity_id=identity.id,
        active=active,
    )
    db._store(Customer).append(customer)
    return customer


def _make_company(db, company_id, name="Barbearia X", slug="barbearia-x"):
    company = SimpleNamespace(
        id=company_id, name=name, slug=slug, timezone="America/Sao_Paulo",
    )
    db._store(Company).append(company)
    return company


def _make_profile(db, company_id, **kwargs):
    profile = SimpleNamespace(
        company_id=company_id,
        logo_url=kwargs.get("logo_url", "https://cdn/logo.png"),
        address=kwargs.get("address", "Rua A, 123"),
        city=kwargs.get("city", "Goiânia"),
        maps_url=kwargs.get("maps_url", "https://maps/x"),
        whatsapp=kwargs.get("whatsapp", "5562911112222"),
    )
    db._store(CompanyProfile).append(profile)
    return profile


def _make_promotion(db, company_id, **kwargs):
    promo = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id,
        discount_type=kwargs.get("discount_type", "PERCENTAGE"),
        discount_value=kwargs.get("discount_value", Decimal("10")),
        valid_until=kwargs.get("valid_until", None),
    )
    db._store(Promotion).append(promo)
    return promo


def _make_coupon(db, company_id, promotion, customer_id=None,
                 status="ACTIVE", expires_at=None, code="OFF10"):
    coupon = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id,
        promotion_id=promotion.id,
        code=code,
        status=status,
        customer_id=customer_id,
        expires_at=expires_at,
    )
    db._store(Coupon).append(coupon)
    return coupon


def _make_payment(db, customer, created_at=None, status="CONFIRMED",
                  appointment_id=None, coupon_code=None):
    p = SimpleNamespace(
        payment_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        appointment_id=appointment_id,
        net_charged_amount=Decimal("50.00"),
        payment_method="CASH",
        status=status,
        paid_at=_NOW if status == "CONFIRMED" else None,
        created_at=created_at or _NOW,
        coupon_code=coupon_code,
    )
    db._store(Payment).append(p)
    return p


def _make_appointment(db, customer, hours_from_now=48, status="SCHEDULED"):
    start = _NOW + timedelta(hours=hours_from_now)
    a = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        client_id=customer.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status=status,
        services=[SimpleNamespace(
            service_id=uuid.uuid4(), service_name="Corte",
            duration_snapshot=Decimal("30"), price_snapshot=Decimal("50.00"),
        )],
        professional=SimpleNamespace(name="João Barbeiro"),
        total_amount=Decimal("50.00"),
    )
    db._store(Appointment).append(a)
    return a


# ─── 1. GET /portal/companies ─────────────────────────────────────────────────

class TestGetCompanies:
    def test_returns_companies_with_slug_and_profile(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id, name="Barbearia X", slug="barbearia-x")
        _make_profile(db, customer.company_id, address="Rua A, 123", city="Goiânia")

        out = portal_service.get_companies(db, identity.id)
        assert len(out) == 1
        assert out[0]["company_name"] == "Barbearia X"
        assert out[0]["slug"] == "barbearia-x"
        assert out[0]["address"] == "Rua A, 123"
        assert out[0]["city"] == "Goiânia"
        assert out[0]["logo_url"] == "https://cdn/logo.png"

    def test_without_profile_returns_nulls(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)

        out = portal_service.get_companies(db, identity.id)
        assert out[0]["logo_url"] is None
        assert out[0]["address"] is None

    def test_identity_without_customers_returns_empty(self):
        db = FakeDB()
        identity = _make_identity(db)
        assert portal_service.get_companies(db, identity.id) == []

    def test_does_not_include_other_identity_companies(self):
        db = FakeDB()
        identity = _make_identity(db)
        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        _make_company(db, other_customer.company_id, name="Outra")

        assert portal_service.get_companies(db, identity.id) == []


# ─── 2. GET /portal/coupons ───────────────────────────────────────────────────

class TestGetCoupons:
    def test_nominal_and_generic_coupons(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        promo = _make_promotion(db, customer.company_id)
        _make_coupon(db, customer.company_id, promo, customer_id=customer.id, code="MEU10")
        _make_coupon(db, customer.company_id, promo, customer_id=None, code="GERAL10")
        # Cupom nominal de OUTRO cliente — não deve aparecer
        _make_coupon(db, customer.company_id, promo, customer_id=uuid.uuid4(), code="ALHEIO")

        out = portal_service.get_coupons(db, identity.id)
        codes = {c["code"] for c in out}
        assert codes == {"MEU10", "GERAL10"}
        by_code = {c["code"]: c for c in out}
        assert by_code["MEU10"]["is_personal"] is True
        assert by_code["GERAL10"]["is_personal"] is False
        assert by_code["MEU10"]["discount_type"] == "PERCENTAGE"
        assert by_code["MEU10"]["discount_value"] == "10"

    def test_excludes_expired_coupons(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        promo = _make_promotion(db, customer.company_id)
        _make_coupon(db, customer.company_id, promo, code="VENCIDO",
                     expires_at=_NOW - timedelta(days=1))
        _make_coupon(db, customer.company_id, promo, code="VIGENTE",
                     expires_at=_NOW + timedelta(days=1))

        out = portal_service.get_coupons(db, identity.id)
        assert [c["code"] for c in out] == ["VIGENTE"]

    def test_excludes_non_active_status(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        promo = _make_promotion(db, customer.company_id)
        _make_coupon(db, customer.company_id, promo, code="CANC", status="CANCELLED")

        assert portal_service.get_coupons(db, identity.id) == []

    def test_no_customers_returns_empty(self):
        db = FakeDB()
        identity = _make_identity(db)
        assert portal_service.get_coupons(db, identity.id) == []


# ─── 3. GET /portal/payments ──────────────────────────────────────────────────

class TestGetPayments:
    def test_lists_only_identity_payments(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        mine = _make_payment(db, customer, coupon_code="OFF10")

        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        _make_payment(db, other_customer)

        out = portal_service.get_payments(db, identity.id)
        assert out["total"] == 1
        assert out["items"][0]["payment_id"] == str(mine.payment_id)
        assert out["items"][0]["amount"] == "50.00"
        assert out["items"][0]["payment_method"] == "CASH"
        assert out["items"][0]["status"] == "CONFIRMED"
        assert out["items"][0]["coupon_code"] == "OFF10"
        assert out["items"][0]["company_name"] == "Barbearia X"

    def test_pagination(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        for i in range(5):
            _make_payment(db, customer, created_at=_NOW - timedelta(days=i))

        page1 = portal_service.get_payments(db, identity.id, page=1, page_size=2)
        page3 = portal_service.get_payments(db, identity.id, page=3, page_size=2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert len(page3["items"]) == 1

    def test_no_customers_returns_empty_page(self):
        db = FakeDB()
        identity = _make_identity(db)
        out = portal_service.get_payments(db, identity.id)
        assert out == {"items": [], "page": 1, "page_size": 20, "total": 0}


# ─── 4. GET /portal/appointments/{id} ─────────────────────────────────────────

class TestAppointmentDetail:
    def test_detail_with_address_and_flags(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        _make_profile(db, customer.company_id)
        appt = _make_appointment(db, customer)

        out = portal_service.get_appointment_detail(db, identity.id, appt.id)
        assert out["appointment_id"] == str(appt.id)
        assert out["company_name"] == "Barbearia X"
        assert out["company_address"] == "Rua A, 123"
        assert out["company_city"] == "Goiânia"
        assert out["company_maps_url"] == "https://maps/x"
        assert out["company_whatsapp"] == "5562911112222"
        assert out["company_timezone"] == "America/Sao_Paulo"
        assert out["professional_name"] == "João Barbeiro"
        assert out["services"] == [
            {"service_name": "Corte", "duration_minutes": 30, "price": "50.00"}
        ]
        assert out["can_cancel"] is True
        assert out["can_reschedule"] is True

    def test_completed_appointment_cannot_act(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        appt = _make_appointment(db, customer, status="COMPLETED")

        out = portal_service.get_appointment_detail(db, identity.id, appt.id)
        assert out["can_cancel"] is False
        assert out["can_reschedule"] is False

    def test_404_when_not_owned(self):
        db = FakeDB()
        identity = _make_identity(db)
        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        appt = _make_appointment(db, other_customer)

        with pytest.raises(HTTPException) as exc:
            portal_service.get_appointment_detail(db, identity.id, appt.id)
        assert exc.value.status_code == 404

    def test_404_when_missing(self):
        db = FakeDB()
        identity = _make_identity(db)
        with pytest.raises(HTTPException) as exc:
            portal_service.get_appointment_detail(db, identity.id, uuid.uuid4())
        assert exc.value.status_code == 404


# ─── 5. POST /portal/appointments/{id}/cancel ─────────────────────────────────

class TestCancelPortal:
    def _cancel(self, db, identity, appointment_id):
        return portal_router.cancel_appointment_portal(
            appointment_id, identity=identity, db=db,
        )

    def test_scheduled_cancels_with_deposit_flag(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer)

        captured = {}

        def _fake_cancel(db_, company_id, appointment_id, user_id=None,
                         reason=None, skip_policy=False):
            captured.update(company_id=company_id, reason=reason,
                            skip_policy=skip_policy, user_id=user_id)
            appt.status = "CANCELLED"
            return appt

        monkeypatch.setattr(
            "app.modules.appointments.service.cancel_appointment", _fake_cancel,
        )
        monkeypatch.setattr(
            portal_service, "_compute_deposit_retained", lambda db_, a: False,
        )

        out = self._cancel(db, identity, appt.id)
        assert out["status"] == "CANCELLED"
        assert out["deposit_retained"] is False
        assert captured["skip_policy"] is True
        assert captured["user_id"] is None
        assert "Portal" in captured["reason"]

    def test_deposit_retained_true_outside_window(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer, hours_from_now=2)  # start em 2h
        _make_payment(db, customer, status="CONFIRMED", appointment_id=appt.id)

        policy = SimpleNamespace(refundable_until_hours_before=24)
        monkeypatch.setattr(
            "app.modules.payments.deposit_service.resolve_deposit_policy",
            lambda service_id, company_id, db_: policy,
        )
        monkeypatch.setattr(
            "app.modules.appointments.service.cancel_appointment",
            lambda *a, **k: SimpleNamespace(id=appt.id, status="CANCELLED"),
        )

        out = self._cancel(db, identity, appt.id)
        assert out["deposit_retained"] is True

    def test_deposit_not_retained_within_window(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer, hours_from_now=72)  # start em 72h
        _make_payment(db, customer, status="CONFIRMED", appointment_id=appt.id)

        policy = SimpleNamespace(refundable_until_hours_before=24)
        monkeypatch.setattr(
            "app.modules.payments.deposit_service.resolve_deposit_policy",
            lambda service_id, company_id, db_: policy,
        )
        monkeypatch.setattr(
            "app.modules.appointments.service.cancel_appointment",
            lambda *a, **k: SimpleNamespace(id=appt.id, status="CANCELLED"),
        )

        out = self._cancel(db, identity, appt.id)
        assert out["deposit_retained"] is False

    def test_deposit_false_without_policy_or_payment(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer, hours_from_now=2)
        # Sem DepositPolicy (resolve → None) e sem Payment CONFIRMED
        monkeypatch.setattr(
            "app.modules.payments.deposit_service.resolve_deposit_policy",
            lambda service_id, company_id, db_: None,
        )
        assert portal_service._compute_deposit_retained(db, appt) is False

    def test_non_scheduled_422(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer, status="COMPLETED")

        with pytest.raises(HTTPException) as exc:
            self._cancel(db, identity, appt.id)
        assert exc.value.status_code == 422

    def test_not_owned_404(self):
        db = FakeDB()
        identity = _make_identity(db)
        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        appt = _make_appointment(db, other_customer)

        with pytest.raises(HTTPException) as exc:
            self._cancel(db, identity, appt.id)
        assert exc.value.status_code == 404


# ─── 6. POST /portal/appointments/{id}/reschedule ─────────────────────────────

class TestReschedulePortal:
    def _reschedule(self, db, identity, appointment_id, start_at=None):
        from app.modules.portal.schemas import PortalRescheduleRequest
        body = PortalRescheduleRequest(start_at=start_at or (_NOW + timedelta(days=3)))
        return portal_router.reschedule_appointment_portal(
            appointment_id, body, identity=identity, db=db,
        )

    def test_reschedules(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer)
        new_start = _NOW + timedelta(days=3)

        captured = {}

        def _fake_reschedule(db_, company_id, appointment_id, data,
                             user_id=None, skip_policy=False,
                             bypass_working_hours=False):
            captured.update(skip_policy=skip_policy,
                            bypass_working_hours=bypass_working_hours,
                            start_at=data.start_at)
            appt.start_at = data.start_at
            return appt

        monkeypatch.setattr(
            "app.modules.appointments.service.reschedule_appointment",
            _fake_reschedule,
        )

        out = self._reschedule(db, identity, appt.id, start_at=new_start)
        assert out["status"] == "SCHEDULED"
        assert out["start_at"] == new_start.isoformat()
        assert captured["skip_policy"] is True
        assert captured["bypass_working_hours"] is False

    def test_conflict_409_becomes_422(self, monkeypatch):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer)

        def _conflict(*a, **k):
            raise HTTPException(status_code=409, detail="Horário já ocupado")

        monkeypatch.setattr(
            "app.modules.appointments.service.reschedule_appointment", _conflict,
        )
        with pytest.raises(HTTPException) as exc:
            self._reschedule(db, identity, appt.id)
        assert exc.value.status_code == 422

    def test_non_scheduled_422(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        appt = _make_appointment(db, customer, status="CANCELLED")

        with pytest.raises(HTTPException) as exc:
            self._reschedule(db, identity, appt.id)
        assert exc.value.status_code == 422

    def test_not_owned_404(self):
        db = FakeDB()
        identity = _make_identity(db)
        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        appt = _make_appointment(db, other_customer)

        with pytest.raises(HTTPException) as exc:
            self._reschedule(db, identity, appt.id)
        assert exc.value.status_code == 404


# ─── 7–8. Checkout com JWT portal opcional ────────────────────────────────────

def _company_ns():
    return SimpleNamespace(id=uuid.uuid4(), name="Barbearia X",
                           timezone="America/Sao_Paulo")


def _patch_online_booking(monkeypatch, company):
    from app.modules.booking import router as booking_router
    monkeypatch.setattr(
        booking_router, "_require_online_booking",
        lambda slug, db: (company, SimpleNamespace(online_booking_enabled=True)),
    )


class TestCheckoutPortalIdentity:
    def test_authenticated_uses_identity_phone_and_portal_consent(self, monkeypatch):
        from app.modules.booking import router as booking_router
        from app.modules.booking.checkout_schemas import CheckoutRequest
        import app.modules.identity.resolver as resolver_module
        import app.modules.identity.consent_service as consent_service

        company = _company_ns()
        _patch_online_booking(monkeypatch, company)
        identity = _make_identity()
        customer = SimpleNamespace(id=uuid.uuid4(), identity_id=identity.id)

        captured = {}
        monkeypatch.setattr(
            resolver_module.resolver, "resolve_for_tenant",
            lambda db, raw_phone, company_id, name: (
                captured.update(raw_phone=raw_phone, name=name) or (customer, True)
            ),
        )
        consent_captured = {}
        monkeypatch.setattr(
            consent_service, "grant_consent",
            lambda db, identity_id, company_id, ctype, channel, source, notes=None:
                consent_captured.update(source=source),
        )
        # Validação estrita NUNCA deve rodar no fluxo autenticado
        monkeypatch.setattr(
            resolver_module, "validate_user_phone_input",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("validate_user_phone_input não deve ser chamado")
            ),
        )

        body = CheckoutRequest(customer_phone="00-telefone-invalido-00")
        out = booking_router.unified_checkout(
            "barbearia-x", body, portal_identity=identity, db=MagicMock(),
        )
        # phone do body IGNORADO — identity tem precedência absoluta
        assert captured["raw_phone"] == identity.phone_e164
        assert captured["name"] == identity.name
        assert consent_captured["source"] == consent_service.SourceChannel.PORTAL
        assert out.customer_id == customer.id

    def test_authenticated_reuses_existing_customer_no_consent(self, monkeypatch):
        from app.modules.booking import router as booking_router
        from app.modules.booking.checkout_schemas import CheckoutRequest
        import app.modules.identity.resolver as resolver_module
        import app.modules.identity.consent_service as consent_service

        company = _company_ns()
        _patch_online_booking(monkeypatch, company)
        identity = _make_identity()
        customer = SimpleNamespace(id=uuid.uuid4(), identity_id=identity.id)

        monkeypatch.setattr(
            resolver_module.resolver, "resolve_for_tenant",
            lambda db, raw_phone, company_id, name: (customer, False),
        )
        monkeypatch.setattr(
            consent_service, "grant_consent",
            lambda *a, **k: (_ for _ in ()).throw(
                AssertionError("consent não deve ser concedido para customer existente")
            ),
        )

        out = booking_router.unified_checkout(
            "barbearia-x", CheckoutRequest(), portal_identity=identity, db=MagicMock(),
        )
        assert out.customer_id == customer.id

    def test_anonymous_without_name_or_phone_422(self, monkeypatch):
        from app.modules.booking import router as booking_router
        from app.modules.booking.checkout_schemas import CheckoutRequest

        company = _company_ns()
        _patch_online_booking(monkeypatch, company)

        with pytest.raises(HTTPException) as exc:
            booking_router.unified_checkout(
                "barbearia-x", CheckoutRequest(customer_name="João"),
                portal_identity=None, db=MagicMock(),
            )
        assert exc.value.status_code == 422

        with pytest.raises(HTTPException) as exc:
            booking_router.unified_checkout(
                "barbearia-x", CheckoutRequest(customer_phone="62988887777"),
                portal_identity=None, db=MagicMock(),
            )
        assert exc.value.status_code == 422

    def test_anonymous_still_validates_phone(self, monkeypatch):
        from app.modules.booking import router as booking_router
        from app.modules.booking.checkout_schemas import CheckoutRequest

        company = _company_ns()
        _patch_online_booking(monkeypatch, company)

        body = CheckoutRequest(customer_name="João", customer_phone="5562985657312")
        with pytest.raises(HTTPException) as exc:
            booking_router.unified_checkout(
                "barbearia-x", body, portal_identity=None, db=MagicMock(),
            )
        assert exc.value.status_code == 422  # DDI rejeitado no fluxo anônimo


class TestPortalIdentityOptionalDependency:
    def test_no_credentials_returns_none(self):
        assert get_current_portal_identity_optional(credentials=None, db=FakeDB()) is None

    def test_invalid_token_401(self):
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="lixo")
        with pytest.raises(HTTPException) as exc:
            get_current_portal_identity_optional(credentials=creds, db=FakeDB())
        assert exc.value.status_code == 401

    def test_tenant_token_401(self):
        from app.core.security import create_access_token
        token = create_access_token({
            "sub": str(uuid.uuid4()), "email": "owner@tenant.com",
            "company_id": str(uuid.uuid4()), "role": "OWNER",
        })
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as exc:
            get_current_portal_identity_optional(credentials=creds, db=FakeDB())
        assert exc.value.status_code == 401

    def test_valid_portal_token_returns_identity(self):
        from app.modules.portal.auth_service import create_portal_token

        db = FakeDB()
        identity = PaladinoIdentity(
            id=uuid.uuid4(), phone_e164="+5562988887777",
            phone_national_normalized="62988887777", possible_aliases=[],
        )
        db._store(PaladinoIdentity).append(identity)
        token = create_portal_token(identity.id)
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        out = get_current_portal_identity_optional(credentials=creds, db=db)
        assert out is identity

    def test_valid_token_unknown_identity_401(self):
        from app.modules.portal.auth_service import create_portal_token

        token = create_portal_token(uuid.uuid4())
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        with pytest.raises(HTTPException) as exc:
            get_current_portal_identity_optional(credentials=creds, db=FakeDB())
        assert exc.value.status_code == 401
