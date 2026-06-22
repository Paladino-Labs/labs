"""
Testes das dívidas de backend Fases 5A–5B (B1–B6).

Usa FakeDB in-memory (avalia BinaryExpressions do SQLAlchemy contra objetos
Python) — sem banco PostgreSQL real (padrão do projeto). O FakeDB roteia
stores por classe passada a query()/_store(); os objetos podem ser
SimpleNamespace (mesmo padrão de tests/test_sprint_d_portal.py).

Cobertura:
  B1 — company_name presente em dashboard/history/credits/subscriptions
  B2 — service_name no crédito (resolução via origem + fallback de rótulo)
  B3 — GET consumptions retorna lista (404 se credit_id inválido/de outra identity)
  B4 — filtro status em get_history (COMPLETED filtra; inválido → 422)
  B5 — resume muda status para ACTIVE (404 se de outra identity; 403 sem gate)
  B6 — list_products retorna só ativos (404 se slug inválido)
"""
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.infrastructure.db.models import (
    Appointment,
    Company,
    CompanySettings,
    Customer,
    CustomerCredit,
    CustomerCreditConsumption,
    Package,
    PackagePurchase,
    Product,
    Service,
    TenantConfig,
)
from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
from app.modules.portal import service as portal_service


# ─── FakeDB (espelha tests/test_sprint_d_portal.py) ──────────────────────────

def _criterion_matches(obj, c) -> bool:
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


# ─── Builders ─────────────────────────────────────────────────────────────────

def _identity_id():
    return uuid.uuid4()


def _company(db, name="Barbearia do Zé", slug="ze", active=True):
    comp = SimpleNamespace(id=uuid.uuid4(), name=name, slug=slug, active=active)
    db._store(Company).append(comp)
    return comp


def _customer(db, identity_id, company_id):
    cust = SimpleNamespace(
        id=uuid.uuid4(), company_id=company_id, identity_id=identity_id, active=True,
    )
    db._store(Customer).append(cust)
    return cust


def _appointment(db, customer, hours=-10, status="COMPLETED", service="Corte", prof="João"):
    start = datetime.now(timezone.utc) + timedelta(hours=hours)
    a = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=customer.company_id,
        client_id=customer.id,
        start_at=start,
        end_at=start + timedelta(minutes=30),
        status=status,
        services=[SimpleNamespace(service_name=service)],
        professional=SimpleNamespace(name=prof),
        total_amount=Decimal("50.00"),
    )
    db._store(Appointment).append(a)
    return a


def _credit(db, customer, entitlement="PACKAGE", source_id=None, status="ACTIVE",
            service_id=None, product_id=None):
    c = SimpleNamespace(
        credit_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        entitlement_type=entitlement,
        source_id=source_id,
        service_id=service_id,
        product_id=product_id,
        total_cotas=4,
        remaining_cotas=2,
        status=status,
        granted_at=datetime.now(timezone.utc),
        expires_at=None,
    )
    db._store(CustomerCredit).append(c)
    return c


def _subscription(db, customer, status="ACTIVE"):
    s = SimpleNamespace(
        subscription_id=uuid.uuid4(),
        company_id=customer.company_id,
        customer_id=customer.id,
        plan=SimpleNamespace(name="Plano Mensal"),
        status=status,
        next_billing_at=datetime.now(timezone.utc) + timedelta(days=15),
        paused_at=datetime.now(timezone.utc) if status == "PAUSED" else None,
        cancelled_at=None,
    )
    db._store(CustomerSubscription).append(s)
    return s


def _tenant_config(db, company_id, overrides=None):
    cfg = SimpleNamespace(company_id=company_id, permission_overrides=overrides or {})
    db._store(TenantConfig).append(cfg)
    return cfg


# ─── B1 — company_name ────────────────────────────────────────────────────────

class TestB1CompanyName:
    def test_dashboard_includes_company_name(self):
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db, name="Barbearia Premium")
        cust = _customer(db, ident, comp.id)
        _appointment(db, cust, hours=24, status="SCHEDULED")
        _credit(db, cust)
        _subscription(db, cust)

        dash = portal_service.get_dashboard(db, ident)
        assert dash["upcoming_appointments"][0]["company_name"] == "Barbearia Premium"
        assert dash["active_credits"][0]["company_name"] == "Barbearia Premium"
        assert dash["active_subscriptions"][0]["company_name"] == "Barbearia Premium"

    def test_history_includes_company_name(self):
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db, name="Studio Hair")
        cust = _customer(db, ident, comp.id)
        _appointment(db, cust, hours=-50, status="COMPLETED")

        result = portal_service.get_history(db, ident)
        assert result["items"][0]["company_name"] == "Studio Hair"

    def test_credits_and_subscriptions_company_name(self):
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db, name="Corte Fino")
        cust = _customer(db, ident, comp.id)
        _credit(db, cust)
        _subscription(db, cust)

        assert portal_service.get_credits(db, ident)[0]["company_name"] == "Corte Fino"
        assert portal_service.get_subscriptions(db, ident)[0]["company_name"] == "Corte Fino"

    def test_company_name_none_when_company_absent(self):
        """Sem Company no store → company_name None (sem crash)."""
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _credit(db, cust)
        assert portal_service.get_credits(db, ident)[0]["company_name"] is None


# ─── B2 — service_name nos créditos ───────────────────────────────────────────

class TestB2ServiceName:
    def test_fallback_label_when_no_source(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _credit(db, cust, entitlement="PACKAGE", source_id=None)
        assert portal_service.get_credits(db, ident)[0]["service_name"] == "Pacote"

    def test_fallback_label_grant_cota(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _credit(db, cust, entitlement="GRANT_COTA", source_id=None)
        assert portal_service.get_credits(db, ident)[0]["service_name"] == "Cota cortesia"

    def test_resolves_service_name_from_credit_service_id(self):
        """Sprint 26: CustomerCredit.service_id → Service.name (FK direta)."""
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db)
        cust = _customer(db, ident, comp.id)

        service = SimpleNamespace(id=uuid.uuid4(), name="Barba Completa")
        db._store(Service).append(service)

        _credit(db, cust, entitlement="PACKAGE", service_id=service.id)
        assert portal_service.get_credits(db, ident)[0]["service_name"] == "Barba Completa"

    def test_resolves_product_name_from_credit_product_id(self):
        """Sprint 26: CustomerCredit.product_id → Product.name (FK direta)."""
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db)
        cust = _customer(db, ident, comp.id)

        product = SimpleNamespace(id=uuid.uuid4(), name="Pomada Modeladora")
        db._store(Product).append(product)

        _credit(db, cust, entitlement="SUBSCRIPTION", product_id=product.id)
        assert portal_service.get_credits(db, ident)[0]["service_name"] == "Pomada Modeladora"


# ─── B3 — consumptions ────────────────────────────────────────────────────────

class TestB3Consumptions:
    def test_returns_consumptions_with_appointment_data(self):
        db = FakeDB()
        ident = _identity_id()
        comp = _company(db)
        cust = _customer(db, ident, comp.id)
        credit = _credit(db, cust)
        appt = _appointment(db, cust, hours=-5, status="COMPLETED", service="Corte", prof="Maria")
        cons = SimpleNamespace(
            consumption_id=uuid.uuid4(),
            credit_id=credit.credit_id,
            company_id=comp.id,
            customer_id=cust.id,
            appointment_id=appt.id,
            consumed_at=datetime.now(timezone.utc),
        )
        db._store(CustomerCreditConsumption).append(cons)

        result = portal_service.get_credit_consumptions(db, ident, credit.credit_id)
        assert len(result) == 1
        assert result[0]["service_name"] == "Corte"
        assert result[0]["professional_name"] == "Maria"
        assert result[0]["quantity_used"] == 1
        assert result[0]["appointment_id"] == str(appt.id)

    def test_empty_list_when_no_consumptions(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        credit = _credit(db, cust)
        assert portal_service.get_credit_consumptions(db, ident, credit.credit_id) == []

    def test_invalid_credit_id_404(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            portal_service.get_credit_consumptions(db, _identity_id(), uuid.uuid4())
        assert exc.value.status_code == 404

    def test_credit_of_other_identity_404(self):
        db = FakeDB()
        owner = _identity_id()
        intruder = _identity_id()
        cust = _customer(db, owner, uuid.uuid4())
        credit = _credit(db, cust)
        with pytest.raises(HTTPException) as exc:
            portal_service.get_credit_consumptions(db, intruder, credit.credit_id)
        assert exc.value.status_code == 404


# ─── B4 — filtro status no history ────────────────────────────────────────────

class TestB4HistoryStatusFilter:
    def test_filters_by_status(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _appointment(db, cust, hours=-100, status="COMPLETED")
        _appointment(db, cust, hours=-50, status="CANCELLED")

        result = portal_service.get_history(db, ident, status="COMPLETED")
        assert result["total"] == 1
        assert result["items"][0]["status"] == "COMPLETED"

    def test_status_lowercase_normalized(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _appointment(db, cust, hours=-100, status="NO_SHOW")
        result = portal_service.get_history(db, ident, status="no_show")
        assert result["total"] == 1

    def test_invalid_status_422(self):
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            portal_service.get_history(db, _identity_id(), status="FOO")
        assert exc.value.status_code == 422

    def test_valid_nonhistory_status_returns_empty(self):
        """SCHEDULED é válido mas não-histórico → lista vazia, sem 422."""
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        _appointment(db, cust, hours=-100, status="COMPLETED")
        result = portal_service.get_history(db, ident, status="SCHEDULED")
        assert result["total"] == 0


# ─── B5 — resume de assinatura ────────────────────────────────────────────────

class TestB5Resume:
    def test_resume_sets_active(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        sub = _subscription(db, cust, status="PAUSED")
        _tenant_config(db, cust.company_id, {"allow_subscription_pause": True})

        result = portal_service.resume_subscription(db, ident, sub.subscription_id)
        assert sub.status == "ACTIVE"
        assert result["status"] == "ACTIVE"

    def test_resume_blocked_when_tenant_disallows(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        sub = _subscription(db, cust, status="PAUSED")
        _tenant_config(db, cust.company_id)  # default False

        with pytest.raises(HTTPException) as exc:
            portal_service.resume_subscription(db, ident, sub.subscription_id)
        assert exc.value.status_code == 403
        assert sub.status == "PAUSED"

    def test_resume_of_other_identity_404(self):
        db = FakeDB()
        owner = _identity_id()
        intruder = _identity_id()
        cust = _customer(db, owner, uuid.uuid4())
        sub = _subscription(db, cust, status="PAUSED")

        with pytest.raises(HTTPException) as exc:
            portal_service.resume_subscription(db, intruder, sub.subscription_id)
        assert exc.value.status_code == 404

    def test_resume_non_paused_422(self):
        db = FakeDB()
        ident = _identity_id()
        cust = _customer(db, ident, uuid.uuid4())
        sub = _subscription(db, cust, status="ACTIVE")
        _tenant_config(db, cust.company_id, {"allow_subscription_pause": True})

        with pytest.raises(HTTPException) as exc:
            portal_service.resume_subscription(db, ident, sub.subscription_id)
        assert exc.value.status_code == 422


# ─── B6 — GET /booking/{slug}/products ────────────────────────────────────────

class TestB6PublicProducts:
    def _settings(self, db, company_id, enabled=True):
        db._store(CompanySettings).append(
            SimpleNamespace(company_id=company_id, online_booking_enabled=enabled)
        )

    def _product(self, db, company_id, name, active=True, stock=5, price="20.00"):
        p = SimpleNamespace(
            id=uuid.uuid4(), company_id=company_id, name=name,
            description=None, price=Decimal(price), image_url=None,
            active=active, stock=stock,
        )
        db._store(Product).append(p)
        return p

    def test_returns_only_active_products(self):
        from app.modules.booking.router import list_products
        db = FakeDB()
        comp = _company(db, slug="barbearia-x")
        self._settings(db, comp.id)
        self._product(db, comp.id, "Pomada", active=True, stock=10)
        self._product(db, comp.id, "Shampoo Inativo", active=False, stock=10)

        result = list_products("barbearia-x", db=db)
        names = [p.name for p in result]
        assert names == ["Pomada"]
        assert result[0].available is True

    def test_available_false_when_out_of_stock(self):
        from app.modules.booking.router import list_products
        db = FakeDB()
        comp = _company(db, slug="barbearia-y")
        self._settings(db, comp.id)
        self._product(db, comp.id, "Cera", active=True, stock=0)
        result = list_products("barbearia-y", db=db)
        assert result[0].available is False

    def test_available_true_when_stock_none(self):
        from app.modules.booking.router import list_products
        db = FakeDB()
        comp = _company(db, slug="barbearia-z")
        self._settings(db, comp.id)
        self._product(db, comp.id, "Loção", active=True, stock=None)
        result = list_products("barbearia-z", db=db)
        assert result[0].available is True

    def test_invalid_slug_404(self):
        from app.modules.booking.router import list_products
        db = FakeDB()
        with pytest.raises(HTTPException) as exc:
            list_products("nao-existe", db=db)
        assert exc.value.status_code == 404

    def test_booking_disabled_403(self):
        from app.modules.booking.router import list_products
        db = FakeDB()
        comp = _company(db, slug="barbearia-off")
        self._settings(db, comp.id, enabled=False)
        with pytest.raises(HTTPException) as exc:
            list_products("barbearia-off", db=db)
        assert exc.value.status_code == 403
