"""
Portal — vendas de produto (Sprint B produtos): 3 visões da mesma tabela
product_sales via GET /portal/product-sales?status=.

FakeDB in-memory (padrão test_portal_camada2) — sem PostgreSQL real.
NÃO importa app.main (contaminação de ordenação de test_sprint2_rbac).

Casos:
  1. Sem status → histórico completo (todas as vendas da identity)
  2. ?status=RESERVED → só RESERVED
  3. ?status=PURCHASED → só PURCHASED
  4. Paginação (total correto, offset)
  5. Isolamento — venda de outra identity não aparece
  6. Identity sem vendas → lista vazia
  7. Cross-tenant: 2 empresas da mesma identity juntas, company_name correto
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.infrastructure.db.models import (
    Company,
    Customer,
    PaladinoIdentity,
    ProductSale,
)
from app.modules.portal import service as portal_service

_NOW = datetime.now(timezone.utc)


# ─── FakeDB (padrão test_portal_camada2) ──────────────────────────────────────

def _criterion_matches(obj, c) -> bool:
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

    def _store(self, model):
        return self.stores.setdefault(model, [])

    def query(self, model):
        return FakeQuery(self._store(model))


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_identity(db):
    identity = SimpleNamespace(id=uuid.uuid4())
    db._store(PaladinoIdentity).append(identity)
    return identity


def _make_customer(db, identity, company_id=None, active=True):
    customer = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        identity_id=identity.id,
        active=active,
    )
    db._store(Customer).append(customer)
    return customer


def _make_company(db, company_id, name="Barbearia X"):
    company = SimpleNamespace(id=company_id, name=name)
    db._store(Company).append(company)
    return company


def _make_sale(db, customer, status="RESERVED", product_name="Pomada",
               quantity=1, unit_price="30.00", created_at=None,
               picked_up_at=None):
    sale = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        product_id=uuid.uuid4(),
        payment_id=None,
        product_name=product_name,
        quantity=quantity,
        unit_price=Decimal(unit_price),
        total_price=Decimal(unit_price) * quantity,
        status=status,
        created_at=created_at or _NOW,
        picked_up_at=picked_up_at,
    )
    db._store(ProductSale).append(sale)
    return sale


# ─── 1. Histórico completo ────────────────────────────────────────────────────

class TestHistoryView:
    def test_no_status_returns_all_sales(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        _make_sale(db, customer, status="RESERVED")
        _make_sale(db, customer, status="PURCHASED")
        _make_sale(db, customer, status="PICKED_UP", picked_up_at=_NOW)

        out = portal_service.get_product_sales(db, identity.id)
        assert out["total"] == 3
        statuses = {i["status"] for i in out["items"]}
        assert statuses == {"RESERVED", "PURCHASED", "PICKED_UP"}

    def test_item_shape_and_snapshots(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id, name="Barbearia X")
        sale = _make_sale(db, customer, product_name="Pomada Modeladora",
                          quantity=2, unit_price="30.00")

        out = portal_service.get_product_sales(db, identity.id)
        item = out["items"][0]
        assert item["sale_id"] == str(sale.id)
        assert item["company_name"] == "Barbearia X"
        assert item["product_id"] == str(sale.product_id)
        assert item["product_name"] == "Pomada Modeladora"
        assert item["quantity"] == 2
        assert item["unit_price"] == "30.00"
        assert item["total_price"] == "60.00"
        assert item["status"] == "RESERVED"
        assert item["created_at"] == sale.created_at.isoformat()
        assert item["picked_up_at"] is None

    def test_picked_up_at_serialized_when_present(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        picked = _NOW - timedelta(hours=1)
        _make_sale(db, customer, status="PICKED_UP", picked_up_at=picked)

        out = portal_service.get_product_sales(db, identity.id)
        assert out["items"][0]["picked_up_at"] == picked.isoformat()


# ─── 2–3. Filtro por status ───────────────────────────────────────────────────

class TestStatusFilter:
    def _seed(self, db, identity):
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        _make_sale(db, customer, status="RESERVED", product_name="Reservado")
        _make_sale(db, customer, status="PURCHASED", product_name="Comprado")
        _make_sale(db, customer, status="PICKED_UP", product_name="Retirado")
        return customer

    def test_reserved_only(self):
        db = FakeDB()
        identity = _make_identity(db)
        self._seed(db, identity)

        out = portal_service.get_product_sales(db, identity.id, status="RESERVED")
        assert out["total"] == 1
        assert out["items"][0]["product_name"] == "Reservado"
        assert out["items"][0]["status"] == "RESERVED"

    def test_purchased_only(self):
        db = FakeDB()
        identity = _make_identity(db)
        self._seed(db, identity)

        out = portal_service.get_product_sales(db, identity.id, status="PURCHASED")
        assert out["total"] == 1
        assert out["items"][0]["product_name"] == "Comprado"
        assert out["items"][0]["status"] == "PURCHASED"

    def test_picked_up_only(self):
        db = FakeDB()
        identity = _make_identity(db)
        self._seed(db, identity)

        out = portal_service.get_product_sales(db, identity.id, status="PICKED_UP")
        assert out["total"] == 1
        assert out["items"][0]["product_name"] == "Retirado"


# ─── 4. Paginação ─────────────────────────────────────────────────────────────

class TestPagination:
    def test_pagination_total_and_offset(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        for i in range(5):
            _make_sale(db, customer, created_at=_NOW - timedelta(days=i))

        page1 = portal_service.get_product_sales(db, identity.id, page=1, page_size=2)
        page3 = portal_service.get_product_sales(db, identity.id, page=3, page_size=2)
        assert page1["total"] == 5
        assert len(page1["items"]) == 2
        assert page3["total"] == 5
        assert len(page3["items"]) == 1

    def test_pagination_with_status_filter(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        for _ in range(3):
            _make_sale(db, customer, status="RESERVED")
        _make_sale(db, customer, status="PURCHASED")

        out = portal_service.get_product_sales(
            db, identity.id, status="RESERVED", page=1, page_size=2,
        )
        assert out["total"] == 3
        assert len(out["items"]) == 2


# ─── 5–6. Isolamento e identity vazia ─────────────────────────────────────────

class TestIsolation:
    def test_other_identity_sales_do_not_appear(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer = _make_customer(db, identity)
        _make_company(db, customer.company_id)
        mine = _make_sale(db, customer)

        other = _make_identity(db)
        other_customer = _make_customer(db, other)
        _make_sale(db, other_customer, product_name="Alheio")

        out = portal_service.get_product_sales(db, identity.id)
        assert out["total"] == 1
        assert out["items"][0]["sale_id"] == str(mine.id)

    def test_identity_without_sales_returns_empty(self):
        db = FakeDB()
        identity = _make_identity(db)
        _make_customer(db, identity)  # customer sem vendas

        out = portal_service.get_product_sales(db, identity.id)
        assert out == {"items": [], "page": 1, "page_size": 20, "total": 0}

    def test_identity_without_customers_returns_empty(self):
        db = FakeDB()
        identity = _make_identity(db)

        out = portal_service.get_product_sales(db, identity.id)
        assert out == {"items": [], "page": 1, "page_size": 20, "total": 0}


# ─── 7. Cross-tenant ──────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_sales_from_two_companies_with_correct_names(self):
        db = FakeDB()
        identity = _make_identity(db)
        customer_a = _make_customer(db, identity)
        customer_b = _make_customer(db, identity)
        _make_company(db, customer_a.company_id, name="Barbearia A")
        _make_company(db, customer_b.company_id, name="Barbearia B")
        _make_sale(db, customer_a, product_name="Pomada A")
        _make_sale(db, customer_b, product_name="Pomada B")

        out = portal_service.get_product_sales(db, identity.id)
        assert out["total"] == 2
        by_product = {i["product_name"]: i["company_name"] for i in out["items"]}
        assert by_product == {"Pomada A": "Barbearia A", "Pomada B": "Barbearia B"}
