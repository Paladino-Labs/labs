"""
Sprint C (produtos) — aviso de produtos pendentes na conclusão do agendamento.

FakeDB in-memory (padrão test_portal_product_sales) — sem PostgreSQL real.
NÃO importa app.main (contaminação de ordenação de test_sprint2_rbac).

Casos:
  1. get_pending_pickups: RESERVED + PURCHASED entram; PICKED_UP não
  2. get_pending_pickups: filtra por company_id (venda de outra empresa fora)
  3. get_pending_pickups: filtra por customer_id (venda de outro cliente fora)
  4. GET /appointments/{id}/pending-products: has_pending=true + itens mapeados
  5. GET .../pending-products: cliente sem pendência → has_pending=false, items []
  6. GET .../pending-products: agendamento de outra company → 404 (posse)
  7. _send_pos_atendimento: com pendências → dispara product_pickup.reminder
     (além do appointment.completed), com lista de produtos no contexto
  8. _send_pos_atendimento: sem pendências → só appointment.completed
  9. _send_pos_atendimento: falha na 2ª mensagem não propaga (best-effort)
 10. Template product_pickup.reminder presente em _DEFAULT_TEMPLATES
"""
import sys
import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ─── Mock celery antes de qualquer import (padrão test_sprint26_multiitem) ────
if "celery" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.Celery.return_value = _celery_mock
    _celery_mock.task = lambda *a, **kw: (lambda f: f)
    sys.modules["celery"] = _celery_mock
    sys.modules["celery.schedules"] = MagicMock()
    sys.modules["celery.app"] = MagicMock()
    sys.modules["celery.utils"] = MagicMock()
    sys.modules["celery.utils.log"] = MagicMock()

from fastapi import HTTPException

from app.infrastructure.db.models import Appointment, Company
from app.infrastructure.db.models.product_sale import ProductSale
from app.modules.product_sales.service import get_pending_pickups


# ─── FakeDB (padrão test_portal_product_sales) ────────────────────────────────

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

    def close(self):
        pass


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_sale(db, customer_id, company_id, status="RESERVED",
               name="Pomada Modeladora", quantity=1, total="49.90"):
    sale = SimpleNamespace(
        id=uuid.uuid4(),
        customer_id=customer_id,
        company_id=company_id,
        status=status,
        product_name=name,
        quantity=quantity,
        total_price=Decimal(total),
    )
    db._store(ProductSale).append(sale)
    return sale


def _make_appointment(db, company_id, client_id):
    appt = SimpleNamespace(
        id=uuid.uuid4(),
        company_id=company_id,
        client_id=client_id,
    )
    db._store(Appointment).append(appt)
    return appt


# ─── 1–3. get_pending_pickups ─────────────────────────────────────────────────

class TestGetPendingPickups:
    def test_returns_reserved_and_purchased_excludes_picked_up(self):
        db = FakeDB()
        customer_id, company_id = uuid.uuid4(), uuid.uuid4()
        _make_sale(db, customer_id, company_id, status="RESERVED")
        _make_sale(db, customer_id, company_id, status="PURCHASED", name="Óleo de Barba")
        _make_sale(db, customer_id, company_id, status="PICKED_UP", name="Shampoo")

        result = get_pending_pickups(db, customer_id, company_id)

        assert len(result) == 2
        assert {s.status for s in result} == {"RESERVED", "PURCHASED"}
        assert all(s.product_name != "Shampoo" for s in result)

    def test_filters_by_company_id(self):
        db = FakeDB()
        customer_id = uuid.uuid4()
        company_a, company_b = uuid.uuid4(), uuid.uuid4()
        _make_sale(db, customer_id, company_a, status="RESERVED")
        _make_sale(db, customer_id, company_b, status="RESERVED", name="De outra empresa")

        result = get_pending_pickups(db, customer_id, company_a)

        assert len(result) == 1
        assert result[0].company_id == company_a

    def test_filters_by_customer_id(self):
        db = FakeDB()
        company_id = uuid.uuid4()
        customer_a, customer_b = uuid.uuid4(), uuid.uuid4()
        _make_sale(db, customer_a, company_id, status="PURCHASED")
        _make_sale(db, customer_b, company_id, status="PURCHASED", name="De outro cliente")

        result = get_pending_pickups(db, customer_a, company_id)

        assert len(result) == 1
        assert result[0].customer_id == customer_a


# ─── 4–6. GET /appointments/{id}/pending-products ─────────────────────────────

class TestPendingProductsEndpoint:
    def test_has_pending_true_with_items(self):
        from app.modules.appointments.router import pending_products

        db = FakeDB()
        company_id, customer_id = uuid.uuid4(), uuid.uuid4()
        appt = _make_appointment(db, company_id, customer_id)
        _make_sale(db, customer_id, company_id, status="RESERVED",
                   name="Pomada Modeladora", quantity=1, total="49.90")
        _make_sale(db, customer_id, company_id, status="PURCHASED",
                   name="Óleo de Barba", quantity=2, total="79.80")

        resp = pending_products(appt.id, company_id=company_id, db=db)

        assert resp.has_pending is True
        assert len(resp.items) == 2
        first = resp.items[0]
        assert first.product_name == "Pomada Modeladora"
        assert first.quantity == 1
        assert first.status == "RESERVED"
        assert first.total_price == Decimal("49.90")
        assert {i.status for i in resp.items} == {"RESERVED", "PURCHASED"}

    def test_no_pending_returns_false_and_empty(self):
        from app.modules.appointments.router import pending_products

        db = FakeDB()
        company_id, customer_id = uuid.uuid4(), uuid.uuid4()
        appt = _make_appointment(db, company_id, customer_id)
        _make_sale(db, customer_id, company_id, status="PICKED_UP")

        resp = pending_products(appt.id, company_id=company_id, db=db)

        assert resp.has_pending is False
        assert resp.items == []

    def test_appointment_of_other_company_404(self):
        from app.modules.appointments.router import pending_products

        db = FakeDB()
        company_a, company_b = uuid.uuid4(), uuid.uuid4()
        appt = _make_appointment(db, company_a, uuid.uuid4())

        with pytest.raises(HTTPException) as exc_info:
            pending_products(appt.id, company_id=company_b, db=db)
        assert exc_info.value.status_code == 404


# ─── 7–9. _send_pos_atendimento — segunda mensagem WhatsApp ───────────────────

class TestSendPosAtendimentoPendingProducts:
    def _run(self, db, dispatch_mock):
        from app.modules.appointments import router as appt_router

        company_id = db._store(Company)[0].id if db._store(Company) else uuid.uuid4()
        customer_id = (
            db._store(ProductSale)[0].customer_id
            if db._store(ProductSale) else uuid.uuid4()
        )
        with (
            patch("app.infrastructure.db.session.SessionLocal", return_value=db),
            patch("app.core.db_rls.set_rls_context"),
            patch(
                "app.modules.communication.service.communication_service.dispatch",
                dispatch_mock,
            ),
        ):
            appt_router._send_pos_atendimento(
                company_id=company_id,
                customer_id=customer_id,
                phone="5511999998888",
                customer_name="João Silva",
                service_name="Corte",
            )
        return company_id, customer_id

    def test_with_pending_dispatches_second_message(self):
        db = FakeDB()
        company_id, customer_id = uuid.uuid4(), uuid.uuid4()
        db._store(Company).append(
            SimpleNamespace(id=company_id, name="Barbearia X")
        )
        _make_sale(db, customer_id, company_id, status="RESERVED",
                   name="Pomada Modeladora", quantity=1)
        _make_sale(db, customer_id, company_id, status="PURCHASED",
                   name="Óleo de Barba", quantity=2)

        dispatch = MagicMock()
        self._run(db, dispatch)

        assert dispatch.call_count == 2
        events = [c.kwargs["event_type"] for c in dispatch.call_args_list]
        assert events == ["appointment.completed", "product_pickup.reminder"]

        ctx = dispatch.call_args_list[1].kwargs["context"]
        assert ctx["empresa_nome"] == "Barbearia X"
        assert ctx["cliente_nome"] == "João"
        assert "Pomada Modeladora (x1)" in ctx["produtos"]
        assert "pagamento e retirada na loja" in ctx["produtos"]
        assert "Óleo de Barba (x2)" in ctx["produtos"]
        assert "pago — é só retirar" in ctx["produtos"]

    def test_without_pending_only_completed_message(self):
        db = FakeDB()
        company_id, customer_id = uuid.uuid4(), uuid.uuid4()
        db._store(Company).append(
            SimpleNamespace(id=company_id, name="Barbearia X")
        )
        _make_sale(db, customer_id, company_id, status="PICKED_UP")

        dispatch = MagicMock()
        self._run(db, dispatch)

        assert dispatch.call_count == 1
        assert dispatch.call_args.kwargs["event_type"] == "appointment.completed"

    def test_second_message_failure_does_not_propagate(self):
        db = FakeDB()
        company_id, customer_id = uuid.uuid4(), uuid.uuid4()
        db._store(Company).append(
            SimpleNamespace(id=company_id, name="Barbearia X")
        )
        _make_sale(db, customer_id, company_id, status="RESERVED")

        dispatch = MagicMock(
            side_effect=[None, RuntimeError("provider indisponível")]
        )
        # Não deve levantar — o bloco da 2ª mensagem é best-effort
        self._run(db, dispatch)
        assert dispatch.call_count == 2


# ─── 10. Seed do template ─────────────────────────────────────────────────────

class TestTemplateSeed:
    def test_default_templates_include_product_pickup_reminder(self):
        from app.modules.companies.service import _DEFAULT_TEMPLATES

        matches = [
            t for t in _DEFAULT_TEMPLATES
            if t["event_type"] == "product_pickup.reminder"
        ]
        assert len(matches) == 1
        tmpl = matches[0]
        assert tmpl["channel"] == "WHATSAPP"
        assert tmpl["audience"] == "CLIENT"
        assert "{{produtos}}" in tmpl["body_template"]
        assert "{{empresa_nome}}" in tmpl["body_template"]
