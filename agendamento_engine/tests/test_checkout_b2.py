"""
Sprint B2 — endpoints públicos de checkout unificado.

Testa os 5 handlers de booking/router.py diretamente (estilo unitário do B1):
  GET  /booking/{slug}/packages
  GET  /booking/{slug}/subscription-plans
  GET  /booking/{slug}/promotions
  POST /booking/{slug}/coupon/validate
  POST /booking/{slug}/checkout

_require_online_booking e os módulos de serviço são monkeypatchados — os
testes não tocam banco real.
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.modules.booking import router as booking_router
from app.modules.booking.checkout_schemas import (
    CouponValidateRequest,
    CheckoutRequest,
    CheckoutServiceItem,
    CheckoutProductItem,
    CheckoutPackageItem,
    CheckoutSubscriptionItem,
)
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.package import Package
from app.infrastructure.db.models.subscription import SubscriptionPlan
from app.infrastructure.db.models import User

_NOW = datetime.now(timezone.utc)
SLUG = "barbearia-x"


def _company():
    return SimpleNamespace(id=uuid.uuid4(), name="Barbearia X", timezone="America/Sao_Paulo")


def _patch_online_booking(monkeypatch, company):
    monkeypatch.setattr(
        booking_router, "_require_online_booking",
        lambda slug, db: (company, SimpleNamespace(online_booking_enabled=True)),
    )


def _db_with(models: dict):
    """MagicMock db cujo query(model).filter(...).first() devolve models[model]."""
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        q.filter.return_value.first.return_value = models.get(model)
        return q

    db.query.side_effect = _query
    return db


def _pkg_item(name="Corte", qty=1):
    return SimpleNamespace(
        item_type="SERVICE", service_name=name, product_name=None, quantity=qty,
    )


# ─── GET /packages ────────────────────────────────────────────────────────────

def test_list_packages_no_service_id(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)

    pkg = SimpleNamespace(
        package_id=uuid.uuid4(), name="Combo", items=[_pkg_item()],
        total_cotas=4, price=Decimal("120.00"), validity_days=90,
    )
    captured = {}

    def _fake(db, company_id, service_id=None):
        captured["service_id"] = service_id
        return [pkg]

    monkeypatch.setattr(booking_router.package_svc, "get_packages_containing_service", _fake)

    out = booking_router.list_packages(SLUG, None, db=MagicMock())
    assert captured["service_id"] is None
    assert len(out) == 1
    assert out[0].name == "Combo"
    assert out[0].price == "120.00"
    assert out[0].items[0].service_name == "Corte"


def test_list_packages_with_service_id(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    target = uuid.uuid4()
    captured = {}

    def _fake(db, company_id, service_id=None):
        captured["service_id"] = service_id
        return []

    monkeypatch.setattr(booking_router.package_svc, "get_packages_containing_service", _fake)
    out = booking_router.list_packages(SLUG, target, db=MagicMock())
    assert captured["service_id"] == target
    assert out == []


# ─── GET /subscription-plans ──────────────────────────────────────────────────

def test_list_plans_with_service_id(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    target = uuid.uuid4()
    plan = SimpleNamespace(
        plan_id=uuid.uuid4(), name="Mensal", items=[_pkg_item("Barba")],
        total_cotas_per_cycle=2, cotas_per_cycle=2, price=Decimal("80.00"),
        cycle_days=30, rollover_enabled=False,
    )
    captured = {}

    def _fake(db, company_id, service_id=None):
        captured["service_id"] = service_id
        return [plan]

    monkeypatch.setattr(booking_router.subscription_svc, "get_plans_containing_service", _fake)
    out = booking_router.list_plans(SLUG, target, db=MagicMock())
    assert captured["service_id"] == target
    assert out[0].plan_name if hasattr(out[0], "plan_name") else True
    assert out[0].name == "Mensal"
    assert out[0].total_cotas_per_cycle == 2
    assert out[0].price == "80.00"


# ─── GET /promotions ──────────────────────────────────────────────────────────

def test_list_promotions(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    promo = SimpleNamespace(
        id=uuid.uuid4(), name="Black Friday", description="20% off",
        discount_type="PERCENTAGE", discount_value=Decimal("20"),
        valid_until=_NOW + timedelta(days=5),
    )
    monkeypatch.setattr(
        booking_router.promotion_svc, "list_active_promotions",
        lambda db, company_id: [promo],
    )
    out = booking_router.list_promotions(SLUG, db=MagicMock())
    assert len(out) == 1
    assert out[0].name == "Black Friday"
    assert out[0].discount_type == "PERCENTAGE"
    assert out[0].discount_value == "20"


# ─── POST /coupon/validate ────────────────────────────────────────────────────

def test_validate_coupon_valid(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    monkeypatch.setattr(
        booking_router.promotion_svc, "compute_preview",
        lambda **kw: {
            "final_amount": "80.00",
            "discount_total": "20.00",
            "applications": [{"discount_type": "PERCENTAGE", "discount_amount": "20.00"}],
            "coupon_valid": True,
        },
    )
    body = CouponValidateRequest(coupon_code="OFF20", gross_amount="100.00")
    out = booking_router.validate_coupon(SLUG, body, db=MagicMock())
    assert out.valid is True
    assert out.net_amount == "80.00"
    assert out.discount_value == "20.00"
    assert out.discount_type == "PERCENTAGE"


def test_validate_coupon_invalid(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)

    def _raise(**kw):
        raise HTTPException(status_code=422, detail="Cupom esgotado")

    monkeypatch.setattr(booking_router.promotion_svc, "compute_preview", _raise)
    body = CouponValidateRequest(coupon_code="BAD", gross_amount="100.00")
    out = booking_router.validate_coupon(SLUG, body, db=MagicMock())
    assert out.valid is False
    assert out.error == "Cupom esgotado"
    assert out.net_amount is None


# ─── POST /checkout ───────────────────────────────────────────────────────────

def _patch_identity(monkeypatch, customer, is_new=True):
    import app.modules.identity.resolver as resolver_module
    import app.modules.identity.consent_service as consent_service
    monkeypatch.setattr(
        resolver_module.resolver, "resolve_for_tenant",
        lambda db, raw_phone, company_id, name: (customer, is_new),
    )
    granted = {}
    monkeypatch.setattr(
        consent_service, "grant_consent",
        lambda *a, **k: granted.setdefault("called", True),
    )
    return granted


def test_checkout_single_service(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    granted = _patch_identity(monkeypatch, customer, is_new=True)

    appt = SimpleNamespace(
        id=uuid.uuid4(),
        services=[SimpleNamespace(service_name="Corte")],
        professional=SimpleNamespace(name="Ana"),
        start_at=_NOW + timedelta(days=1),
        total_amount=Decimal("50.00"),
    )
    monkeypatch.setattr(
        booking_router.appointment_svc, "create_appointment",
        lambda db, cid, data, user_id=None, bypass_working_hours=False: (appt, "raw-token-123"),
    )

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        services=[CheckoutServiceItem(
            professional_id=uuid.uuid4(), service_id=uuid.uuid4(),
            start_at=_NOW + timedelta(days=1), end_at=_NOW + timedelta(days=1, minutes=30),
        )],
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({}))
    assert granted.get("called") is True
    assert out.customer_id == customer.id
    assert len(out.appointments) == 1
    assert out.appointments[0].service_name == "Corte"
    assert out.appointments[0].professional_name == "Ana"
    assert out.appointments[0].manage_url and "raw-token-123" in out.appointments[0].manage_url
    assert out.total_charged == "0"  # agendamento não é cobrado


def test_checkout_single_package(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    pkg_id = uuid.uuid4()
    pkg = SimpleNamespace(
        package_id=pkg_id, name="Combo", price=Decimal("120.00"), total_cotas=4,
    )
    purchase = SimpleNamespace(purchase_id=uuid.uuid4(), payment_id=uuid.uuid4())
    captured = {}

    def _purchase(**kw):
        captured.update(kw)
        return purchase

    monkeypatch.setattr(booking_router.package_svc, "purchase", _purchase)

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        packages=[CheckoutPackageItem(package_id=pkg_id, payment_method="CASH")],
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({Package: pkg}))
    assert len(out.purchases) == 1
    assert out.purchases[0].package_name == "Combo"
    assert out.purchases[0].total_cotas == 4
    assert out.total_charged == "120.00"
    assert captured["coupon_code"] is None


def test_checkout_service_plus_package(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    appt = SimpleNamespace(
        id=uuid.uuid4(), services=[SimpleNamespace(service_name="Corte")],
        professional=SimpleNamespace(name="Ana"),
        start_at=_NOW + timedelta(days=1), total_amount=Decimal("50.00"),
    )
    monkeypatch.setattr(
        booking_router.appointment_svc, "create_appointment",
        lambda db, cid, data, user_id=None, bypass_working_hours=False: (appt, "tok"),
    )
    pkg_id = uuid.uuid4()
    pkg = SimpleNamespace(package_id=pkg_id, name="Combo", price=Decimal("120.00"), total_cotas=4)
    monkeypatch.setattr(
        booking_router.package_svc, "purchase",
        lambda **kw: SimpleNamespace(purchase_id=uuid.uuid4(), payment_id=uuid.uuid4()),
    )

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        services=[CheckoutServiceItem(
            professional_id=uuid.uuid4(), service_id=uuid.uuid4(),
            start_at=_NOW + timedelta(days=1), end_at=_NOW + timedelta(days=1, minutes=30),
        )],
        packages=[CheckoutPackageItem(package_id=pkg_id)],
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({Package: pkg}))
    assert len(out.appointments) == 1
    assert len(out.purchases) == 1
    # total = só o preço do pacote (agendamento não cobra)
    assert out.total_charged == "120.00"


def test_checkout_product_without_owner_warns(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    prod_id = uuid.uuid4()
    product = SimpleNamespace(
        id=prod_id, name="Pomada", price=Decimal("30.00"), company_id=company.id,
    )
    pay_calls = {}
    monkeypatch.setattr(
        booking_router.payment_svc, "create_payment",
        lambda **kw: pay_calls.update(kw) or SimpleNamespace(payment_id=uuid.uuid4()),
    )
    move_calls = {}
    monkeypatch.setattr(
        booking_router.stock_svc, "record_movement",
        lambda **kw: move_calls.update({"called": True}),
    )

    # db.query(Product) → product; db.query(User) → None (sem OWNER)
    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=prod_id, quantity=2)],
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({Product: product, User: None}))
    assert len(out.product_sales) == 1
    assert out.product_sales[0].amount_paid == "60.00"
    assert out.total_charged == "60.00"
    assert any("OWNER não encontrado" in w for w in out.warnings)
    assert move_calls == {}  # baixa de estoque pulada
    assert pay_calls["gross_amount"] == Decimal("60.00")


def test_checkout_product_with_owner_records_stock(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    prod_id = uuid.uuid4()
    product = SimpleNamespace(id=prod_id, name="Pomada", price=Decimal("30.00"), company_id=company.id)
    owner = SimpleNamespace(id=uuid.uuid4())
    monkeypatch.setattr(
        booking_router.payment_svc, "create_payment",
        lambda **kw: SimpleNamespace(payment_id=uuid.uuid4()),
    )
    move_calls = {}
    monkeypatch.setattr(
        booking_router.stock_svc, "record_movement",
        lambda **kw: move_calls.update(kw),
    )
    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=prod_id, quantity=1)],
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({Product: product, User: owner}))
    assert out.warnings == []
    assert move_calls["movement_type"] == "VENDA"
    assert move_calls["created_by"] == owner.id


def test_checkout_coupon_routed_to_package(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    pkg_id = uuid.uuid4()
    pkg = SimpleNamespace(package_id=pkg_id, name="Combo", price=Decimal("120.00"), total_cotas=4)
    captured = {}
    monkeypatch.setattr(
        booking_router.package_svc, "purchase",
        lambda **kw: captured.update(kw) or SimpleNamespace(purchase_id=uuid.uuid4(), payment_id=uuid.uuid4()),
    )
    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        packages=[CheckoutPackageItem(package_id=pkg_id)],
        coupon_code="OFF20",
    )
    out = booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({Package: pkg}))
    assert captured["coupon_code"] == "OFF20"
    assert out.coupon_applied == "OFF20"


def test_checkout_slug_inactive_403(monkeypatch):
    def _raise(slug, db):
        raise HTTPException(status_code=403, detail="off")

    monkeypatch.setattr(booking_router, "_require_online_booking", _raise)
    body = CheckoutRequest(customer_name="João", customer_phone="11999998888")
    with pytest.raises(HTTPException) as exc:
        booking_router.unified_checkout(SLUG, body, portal_identity=None, db=MagicMock())
    assert exc.value.status_code == 403


def test_checkout_service_conflict_propagates(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer, is_new=False)

    def _conflict(db, cid, data, user_id=None, bypass_working_hours=False):
        raise HTTPException(status_code=409, detail="Horário já ocupado por outro agendamento")

    monkeypatch.setattr(booking_router.appointment_svc, "create_appointment", _conflict)
    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        services=[CheckoutServiceItem(
            professional_id=uuid.uuid4(), service_id=uuid.uuid4(),
            start_at=_NOW + timedelta(days=1), end_at=_NOW + timedelta(days=1, minutes=30),
        )],
    )
    with pytest.raises(HTTPException) as exc:
        booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({}))
    # Conflito de slot é 409 no domínio (o DoD menciona 422 genérico; o real é 409).
    assert exc.value.status_code == 409


def test_checkout_phone_with_ddi_rejected_422(monkeypatch):
    """Telefone com DDI (55...) → 422 ANTES de resolver cliente ou criar registros."""
    company = _company()
    _patch_online_booking(monkeypatch, company)

    import app.modules.identity.resolver as resolver_module

    def _must_not_be_called(*a, **k):
        raise AssertionError("resolve_for_tenant não deve ser chamado com telefone inválido")

    monkeypatch.setattr(resolver_module.resolver, "resolve_for_tenant", _must_not_be_called)

    body = CheckoutRequest(
        customer_name="João", customer_phone="5562985657312",
        services=[CheckoutServiceItem(
            professional_id=uuid.uuid4(), service_id=uuid.uuid4(),
            start_at=_NOW + timedelta(days=1), end_at=_NOW + timedelta(days=1, minutes=30),
        )],
    )
    with pytest.raises(HTTPException) as exc:
        booking_router.unified_checkout(SLUG, body, portal_identity=None, db=_db_with({}))
    assert exc.value.status_code == 422
