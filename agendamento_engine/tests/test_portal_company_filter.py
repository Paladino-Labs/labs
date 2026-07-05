"""
Portal — filtro company_id nos endpoints de listagem (padrão de /history).

credits, subscriptions, coupons, payments, product-sales e dashboard aceitam
company_id opcional. O filtro opera SOBRE os customers da identity: company_id
de empresa onde o cliente não é cliente → customer_ids vazio → resultado vazio
(seguro por construção — impossível vazar dados de outra empresa).

FakeDB in-memory (padrão test_portal_camada2) — sem PostgreSQL real.
NÃO importa app.main (contaminação de ordenação de test_sprint2_rbac).

Casos (por endpoint):
  1. Sem company_id → comportamento atual (todas as empresas) — não regride
  2. company_id de empresa da identity → só itens daquela empresa
  3. company_id de empresa alheia → vazio (segurança)
Extras:
  - dashboard: as 3 sub-listas respeitam o filtro simultaneamente
  - product-sales: company_id + status combinam
  - coupons: genéricos do tenant (customer_id NULL) respeitam o filtro
  - payments: total reflete o filtro ANTES da paginação
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.infrastructure.db.models import (
    Appointment,
    Company,
    Coupon,
    Customer,
    CustomerCredit,
    PaladinoIdentity,
    Payment,
    ProductSale,
    Promotion,
)
from app.infrastructure.db.models.subscription import CustomerSubscription
from app.modules.portal import service as portal_service

_NOW = datetime.now(timezone.utc)


# ─── FakeDB (padrão test_portal_camada2) ──────────────────────────────────────

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


def _make_appointment(db, customer, status="SCHEDULED", start_at=None):
    start = start_at or (_NOW + timedelta(days=1))
    appt = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        client_id=customer.id,
        status=status,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        services=[SimpleNamespace(service_name="Corte")],
        professional=None,
        total_amount=Decimal("50.00"),
    )
    db._store(Appointment).append(appt)
    return appt


def _make_credit(db, customer, status="ACTIVE"):
    credit = SimpleNamespace(
        credit_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        entitlement_type="PACKAGE",
        service_id=None,
        product_id=None,
        total_cotas=4,
        remaining_cotas=2,
        status=status,
        granted_at=_NOW,
        expires_at=None,
    )
    db._store(CustomerCredit).append(credit)
    return credit


def _make_subscription(db, customer, status="ACTIVE"):
    sub = SimpleNamespace(
        subscription_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        status=status,
        plan=None,
        next_billing_at=None,
        paused_at=None,
        cancelled_at=None,
    )
    db._store(CustomerSubscription).append(sub)
    return sub


def _make_promotion(db, company_id):
    promo = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id,
        discount_type="PERCENTAGE",
        discount_value=Decimal("10"),
        valid_until=None,
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


def _make_payment(db, customer, created_at=None):
    payment = SimpleNamespace(
        payment_id=uuid.uuid4(),
        customer_id=customer.id,
        net_charged_amount=Decimal("50.00"),
        payment_method="PIX",
        status="CONFIRMED",
        paid_at=None,
        created_at=created_at or _NOW,
        coupon_code=None,
    )
    db._store(Payment).append(payment)
    return payment


def _make_sale(db, customer, status="RESERVED", product_name="Pomada"):
    sale = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        product_id=uuid.uuid4(),
        payment_id=None,
        product_name=product_name,
        quantity=1,
        unit_price=Decimal("30.00"),
        total_price=Decimal("30.00"),
        status=status,
        created_at=_NOW,
        picked_up_at=None,
    )
    db._store(ProductSale).append(sale)
    return sale


def _seed_identity_two_companies(db):
    """Identity cliente das empresas A e B; empresa C é alheia (de outra
    identity — tem dados, mas a identity não é cliente lá)."""
    identity = _make_identity(db)
    customer_a = _make_customer(db, identity)
    customer_b = _make_customer(db, identity)
    _make_company(db, customer_a.company_id, name="Barbearia A")
    _make_company(db, customer_b.company_id, name="Barbearia B")

    stranger = _make_identity(db)
    customer_c = _make_customer(db, stranger)
    _make_company(db, customer_c.company_id, name="Barbearia C")
    return identity, customer_a, customer_b, customer_c


# ─── Dashboard ────────────────────────────────────────────────────────────────

class TestDashboardCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        _make_appointment(db, ca)
        _make_appointment(db, cb)
        _make_credit(db, ca)
        _make_credit(db, cb)
        _make_subscription(db, ca)
        _make_subscription(db, cb)
        # dados na empresa alheia (de outra identity)
        _make_appointment(db, cc)
        _make_credit(db, cc)
        _make_subscription(db, cc)
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, ca, cb, _ = self._seed(db)

        out = portal_service.get_dashboard(db, identity.id)
        assert len(out["upcoming_appointments"]) == 2
        assert len(out["active_credits"]) == 2
        assert len(out["active_subscriptions"]) == 2

    def test_filters_all_three_sublists(self):
        db = FakeDB()
        identity, ca, cb, _ = self._seed(db)

        out = portal_service.get_dashboard(db, identity.id, company_id=ca.company_id)
        assert len(out["upcoming_appointments"]) == 1
        assert len(out["active_credits"]) == 1
        assert len(out["active_subscriptions"]) == 1
        assert out["upcoming_appointments"][0]["company_name"] == "Barbearia A"
        assert out["active_credits"][0]["company_name"] == "Barbearia A"
        assert out["active_subscriptions"][0]["company_name"] == "Barbearia A"

    def test_foreign_company_id_returns_empty(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_dashboard(db, identity.id, company_id=cc.company_id)
        assert out == {
            "upcoming_appointments": [],
            "active_credits": [],
            "active_subscriptions": [],
            "counts": {"coupons": 0, "reserved_products": 0, "payments": 0},
        }

    def test_counts_reflect_company_filter(self):
        """F4b — counts (cupons/produtos reservados/pagamentos) seguem o filtro."""
        db = FakeDB()
        identity, ca, cb, _ = self._seed(db)
        _make_sale(db, ca, status="RESERVED")
        _make_sale(db, cb, status="RESERVED")
        _make_sale(db, cb, status="PURCHASED")  # não conta como reservado
        _make_payment(db, ca)
        _make_payment(db, cb)

        out = portal_service.get_dashboard(db, identity.id)
        assert out["counts"]["reserved_products"] == 2
        assert out["counts"]["payments"] == 2

        out_a = portal_service.get_dashboard(db, identity.id, company_id=ca.company_id)
        assert out_a["counts"]["reserved_products"] == 1
        assert out_a["counts"]["payments"] == 1


# ─── Credits ──────────────────────────────────────────────────────────────────

class TestCreditsCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        _make_credit(db, ca)
        _make_credit(db, cb)
        _make_credit(db, cc)
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, _, _, _ = self._seed(db)

        out = portal_service.get_credits(db, identity.id)
        assert {i["company_name"] for i in out} == {"Barbearia A", "Barbearia B"}

    def test_company_id_restricts_to_that_company(self):
        db = FakeDB()
        identity, ca, _, _ = self._seed(db)

        out = portal_service.get_credits(db, identity.id, company_id=ca.company_id)
        assert len(out) == 1
        assert out[0]["company_name"] == "Barbearia A"

    def test_foreign_company_id_returns_empty(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_credits(db, identity.id, company_id=cc.company_id)
        assert out == []


# ─── Subscriptions ────────────────────────────────────────────────────────────

class TestSubscriptionsCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        _make_subscription(db, ca)
        _make_subscription(db, cb)
        _make_subscription(db, cc)
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, _, _, _ = self._seed(db)

        out = portal_service.get_subscriptions(db, identity.id)
        assert {i["company_name"] for i in out} == {"Barbearia A", "Barbearia B"}

    def test_company_id_restricts_to_that_company(self):
        db = FakeDB()
        identity, _, cb, _ = self._seed(db)

        out = portal_service.get_subscriptions(db, identity.id, company_id=cb.company_id)
        assert len(out) == 1
        assert out[0]["company_name"] == "Barbearia B"

    def test_foreign_company_id_returns_empty(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_subscriptions(db, identity.id, company_id=cc.company_id)
        assert out == []


# ─── Coupons ──────────────────────────────────────────────────────────────────

class TestCouponsCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        promo_a = _make_promotion(db, ca.company_id)
        promo_b = _make_promotion(db, cb.company_id)
        promo_c = _make_promotion(db, cc.company_id)
        _make_coupon(db, ca.company_id, promo_a, customer_id=ca.id, code="NOMINAL-A")
        _make_coupon(db, ca.company_id, promo_a, customer_id=None, code="GENERICO-A")
        _make_coupon(db, cb.company_id, promo_b, customer_id=None, code="GENERICO-B")
        # empresa alheia tem cupons (nominal do stranger + genérico)
        _make_coupon(db, cc.company_id, promo_c, customer_id=cc.id, code="NOMINAL-C")
        _make_coupon(db, cc.company_id, promo_c, customer_id=None, code="GENERICO-C")
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, _, _, _ = self._seed(db)

        out = portal_service.get_coupons(db, identity.id)
        assert {c["code"] for c in out} == {"NOMINAL-A", "GENERICO-A", "GENERICO-B"}

    def test_company_id_restricts_nominal_and_generic(self):
        db = FakeDB()
        identity, ca, _, _ = self._seed(db)

        out = portal_service.get_coupons(db, identity.id, company_id=ca.company_id)
        assert {c["code"] for c in out} == {"NOMINAL-A", "GENERICO-A"}

    def test_generic_coupons_respect_the_filter(self):
        db = FakeDB()
        identity, _, cb, _ = self._seed(db)

        out = portal_service.get_coupons(db, identity.id, company_id=cb.company_id)
        assert {c["code"] for c in out} == {"GENERICO-B"}

    def test_foreign_company_id_returns_empty_even_with_generics(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_coupons(db, identity.id, company_id=cc.company_id)
        assert out == []


# ─── Payments ─────────────────────────────────────────────────────────────────

class TestPaymentsCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        _make_payment(db, ca)
        _make_payment(db, cb)
        _make_payment(db, cc)
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, _, _, _ = self._seed(db)

        out = portal_service.get_payments(db, identity.id)
        assert out["total"] == 2
        assert {i["company_name"] for i in out["items"]} == {"Barbearia A", "Barbearia B"}

    def test_company_id_restricts_to_that_company(self):
        db = FakeDB()
        identity, ca, _, _ = self._seed(db)

        out = portal_service.get_payments(db, identity.id, company_id=ca.company_id)
        assert out["total"] == 1
        assert out["items"][0]["company_name"] == "Barbearia A"

    def test_foreign_company_id_returns_empty(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_payments(db, identity.id, company_id=cc.company_id)
        assert out == {"items": [], "page": 1, "page_size": 20, "total": 0}

    def test_total_reflects_filter_before_pagination(self):
        db = FakeDB()
        identity, ca, cb, _ = _seed_identity_two_companies(db)
        for _ in range(3):
            _make_payment(db, ca)
        _make_payment(db, cb)

        out = portal_service.get_payments(
            db, identity.id, page=1, page_size=2, company_id=ca.company_id,
        )
        assert out["total"] == 3
        assert len(out["items"]) == 2
        assert all(i["company_name"] == "Barbearia A" for i in out["items"])


# ─── Product sales ────────────────────────────────────────────────────────────

class TestProductSalesCompanyFilter:
    def _seed(self, db):
        identity, ca, cb, cc = _seed_identity_two_companies(db)
        _make_sale(db, ca, status="RESERVED", product_name="Reservado A")
        _make_sale(db, ca, status="PURCHASED", product_name="Comprado A")
        _make_sale(db, cb, status="RESERVED", product_name="Reservado B")
        _make_sale(db, cc, status="RESERVED", product_name="Alheio C")
        return identity, ca, cb, cc

    def test_no_company_id_returns_all_companies(self):
        db = FakeDB()
        identity, _, _, _ = self._seed(db)

        out = portal_service.get_product_sales(db, identity.id)
        assert out["total"] == 3
        names = {i["product_name"] for i in out["items"]}
        assert names == {"Reservado A", "Comprado A", "Reservado B"}

    def test_company_id_restricts_to_that_company(self):
        db = FakeDB()
        identity, ca, _, _ = self._seed(db)

        out = portal_service.get_product_sales(db, identity.id, company_id=ca.company_id)
        assert out["total"] == 2
        names = {i["product_name"] for i in out["items"]}
        assert names == {"Reservado A", "Comprado A"}

    def test_company_id_combines_with_status(self):
        db = FakeDB()
        identity, ca, _, _ = self._seed(db)

        out = portal_service.get_product_sales(
            db, identity.id, status="RESERVED", company_id=ca.company_id,
        )
        assert out["total"] == 1
        assert out["items"][0]["product_name"] == "Reservado A"

    def test_foreign_company_id_returns_empty(self):
        db = FakeDB()
        identity, _, _, cc = self._seed(db)

        out = portal_service.get_product_sales(db, identity.id, company_id=cc.company_id)
        assert out == {"items": [], "page": 1, "page_size": 20, "total": 0}
