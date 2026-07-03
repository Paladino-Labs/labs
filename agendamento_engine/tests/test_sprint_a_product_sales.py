"""
Sprint A (produtos) — modelo ProductSale + gravação no checkout.

Testa unified_checkout (booking/router.py) diretamente, estilo unitário do
B1/B2: _require_online_booking e serviços monkeypatchados, db MagicMock —
os ProductSale adicionados são capturados via db.add.call_args_list.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.booking import router as booking_router
from app.modules.booking.checkout_schemas import (
    CheckoutRequest,
    CheckoutProductItem,
    CheckoutPackageItem,
)
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.product_sale import ProductSale
from app.infrastructure.db.models.package import Package
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


def _patch_identity(monkeypatch, customer, is_new=False):
    import app.modules.identity.resolver as resolver_module
    import app.modules.identity.consent_service as consent_service
    monkeypatch.setattr(
        resolver_module.resolver, "resolve_for_tenant",
        lambda db, raw_phone, company_id, name: (customer, is_new),
    )
    monkeypatch.setattr(consent_service, "grant_consent", lambda *a, **k: None)


def _db_with(models: dict):
    """MagicMock db cujo query(model).filter(...).first() devolve models[model].

    Valor list → devolve em sequência (um por chamada, p/ múltiplos produtos).
    """
    db = MagicMock()
    remaining = {m: list(v) if isinstance(v, list) else None for m, v in models.items()}

    def _query(model):
        q = MagicMock()
        if isinstance(models.get(model), list):
            seq = remaining[model]
            q.filter.return_value.first.side_effect = lambda: seq.pop(0) if seq else None
        else:
            q.filter.return_value.first.return_value = models.get(model)
        return q

    db.query.side_effect = _query
    return db


def _added_sales(db):
    return [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ProductSale)]


def _patch_payment_and_stock(monkeypatch, payment_id=None):
    payment = SimpleNamespace(payment_id=payment_id or uuid.uuid4())
    monkeypatch.setattr(
        booking_router.payment_svc, "create_payment", lambda **kw: payment,
    )
    monkeypatch.setattr(
        booking_router.stock_svc, "record_movement", lambda **kw: None,
    )
    return payment


def _product(company, name="Pomada", price="30.00"):
    return SimpleNamespace(
        id=uuid.uuid4(), name=name, price=Decimal(price), company_id=company.id,
    )


# ─── ProductSale criado no checkout ──────────────────────────────────────────

def test_checkout_with_product_creates_reserved_sale(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    payment = _patch_payment_and_stock(monkeypatch)

    product = _product(company)
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: product, User: owner})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=product.id, quantity=2)],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    sales = _added_sales(db)
    assert len(sales) == 1
    sale = sales[0]
    assert sale.status == "RESERVED"
    assert sale.company_id == company.id
    assert sale.payment_id == payment.payment_id


def test_checkout_one_sale_per_product_in_array(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    _patch_payment_and_stock(monkeypatch)

    p1 = _product(company, name="Pomada", price="30.00")
    p2 = _product(company, name="Shampoo", price="45.50")
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: [p1, p2], User: owner})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[
            CheckoutProductItem(product_id=p1.id, quantity=1),
            CheckoutProductItem(product_id=p2.id, quantity=3),
        ],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    sales = _added_sales(db)
    assert len(sales) == 2
    assert {s.product_name for s in sales} == {"Pomada", "Shampoo"}
    assert all(s.status == "RESERVED" for s in sales)


def test_checkout_sale_snapshots(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    _patch_payment_and_stock(monkeypatch)

    product = _product(company, name="Cera Modeladora", price="25.90")
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: product, User: owner})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=product.id, quantity=3)],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    sale = _added_sales(db)[0]
    assert sale.product_id == product.id
    assert sale.product_name == "Cera Modeladora"
    assert sale.quantity == 3
    assert sale.unit_price == Decimal("25.90")
    assert sale.total_price == Decimal("77.70")


def test_checkout_sale_links_customer(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    _patch_payment_and_stock(monkeypatch)

    product = _product(company)
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: product, User: owner})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=product.id, quantity=1)],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    assert _added_sales(db)[0].customer_id == customer.id


def test_checkout_without_products_creates_no_sale(monkeypatch):
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)

    pkg_id = uuid.uuid4()
    pkg = SimpleNamespace(package_id=pkg_id, name="Combo", price=Decimal("120.00"), total_cotas=4)
    monkeypatch.setattr(
        booking_router.package_svc, "purchase",
        lambda **kw: SimpleNamespace(purchase_id=uuid.uuid4(), payment_id=uuid.uuid4()),
    )
    db = _db_with({Package: pkg})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        packages=[CheckoutPackageItem(package_id=pkg_id)],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    assert _added_sales(db) == []


def test_checkout_logged_portal_identity_links_identity_customer(monkeypatch):
    """JWT portal: ProductSale nasce com o customer resolvido da identity."""
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    _patch_payment_and_stock(monkeypatch)

    product = _product(company)
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: product, User: owner})

    portal_identity = SimpleNamespace(
        identity_id=customer.identity_id, phone_e164="+5562999998888", name="Maria",
    )
    body = CheckoutRequest(
        products=[CheckoutProductItem(product_id=product.id, quantity=1)],
    )
    out = booking_router.unified_checkout(
        SLUG, body, portal_identity=portal_identity, db=db,
    )

    sale = _added_sales(db)[0]
    assert sale.customer_id == customer.id
    assert out.customer_id == customer.id


def test_checkout_sale_without_payment_has_null_payment_id(monkeypatch):
    """create_payment devolvendo None → payment_id None (defensivo)."""
    company = _company()
    _patch_online_booking(monkeypatch, company)
    customer = SimpleNamespace(id=uuid.uuid4(), identity_id=uuid.uuid4())
    _patch_identity(monkeypatch, customer)
    monkeypatch.setattr(booking_router.payment_svc, "create_payment", lambda **kw: None)
    monkeypatch.setattr(booking_router.stock_svc, "record_movement", lambda **kw: None)

    product = _product(company)
    owner = SimpleNamespace(id=uuid.uuid4())
    db = _db_with({Product: product, User: owner})

    body = CheckoutRequest(
        customer_name="João", customer_phone="11999998888",
        products=[CheckoutProductItem(product_id=product.id, quantity=1)],
    )
    booking_router.unified_checkout(SLUG, body, portal_identity=None, db=db)

    assert _added_sales(db)[0].payment_id is None
