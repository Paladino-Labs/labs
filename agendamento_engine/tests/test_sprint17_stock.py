"""
Testes Sprint 17 — Estoque + Fornecedores + Payables.

Usa mocks (unittest.mock) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  Custo médio recalculado: 10 un @ R$5 + 5 un @ R$7 → avg_cost = R$5,67
  2.  receive_order cria Payable sem Entry CUSTO (Financial-1)
  3.  record_movement VENDA → Entry CUSTO sem Movement (Financial-1)
  4.  record_movement AJUSTE sem notes → 422
  5.  pay_installment atômico: falha no Movement → nada persiste
  6.  Payable PARTIALLY_PAID → 2 installments pagos em sequência → PAID
  7.  Stock zerado com controle ativo → 422 em VENDA
  8.  DRE: Entry CUSTO aparece em aggregate_dre
  9.  stock_min_alert: stock <= min → evento stock.low_alert publicado
  10. FK expenses.supplier_id → suppliers presente na migration
  11. Cross-tenant: produto/payable de empresa A invisível para B (404)
"""
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

# ─── Mock celery antes de qualquer import ─────────────────────────────────────
if "celery" not in sys.modules:
    _celery_mock = MagicMock()
    _celery_mock.Celery.return_value = _celery_mock
    _celery_mock.task = lambda *a, **kw: (lambda f: f)
    sys.modules["celery"] = _celery_mock
    sys.modules["celery.schedules"] = MagicMock()
    sys.modules["celery.app"] = MagicMock()
    sys.modules["celery.utils"] = MagicMock()
    sys.modules["celery.utils.log"] = MagicMock()

from app.infrastructure.db.models.entry import Entry
from app.infrastructure.db.models.movement import Movement
from app.infrastructure.db.models.payable import Payable, PayableInstallment
from app.infrastructure.db.models.stock_movement import StockMovement
from app.modules.financial_core import service as financial_core
from app.modules.payables import service as payables_service
from app.modules.stock import service as stock_service
from app.modules.stock.service import compute_avg_cost


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_product(company_id=None, stock=0, avg_cost=None, stock_min_alert=None):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.name = "Pomada Modeladora"
    p.active = True
    p.stock = stock
    p.avg_cost = avg_cost
    p.stock_min_alert = stock_min_alert
    p.unit = "un"
    return p


def _make_account(company_id=None):
    a = MagicMock()
    a.account_id = uuid.uuid4()
    a.company_id = company_id or uuid.uuid4()
    a.is_default_inflow = True
    return a


def _make_tenant_config(allow_negative_stock=False):
    c = MagicMock()
    c.allow_negative_stock = allow_negative_stock
    return c


def _make_payable(company_id=None, total_amount=Decimal("100.00"), status="OPEN",
                  paid_amount=Decimal("0")):
    p = MagicMock()
    p.id = uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.total_amount = total_amount
    p.paid_amount = paid_amount
    p.status = status
    p.description = "Compra de estoque"
    p.due_date = date(2026, 6, 20)
    return p


def _make_installment(payable_id, company_id, amount=Decimal("50.00"), number=1):
    i = MagicMock()
    i.id = uuid.uuid4()
    i.payable_id = payable_id
    i.company_id = company_id
    i.amount = amount
    i.installment_number = number
    i.status = "OPEN"
    i.paid_at = None
    i.payment_id = None
    return i


def _make_db(objects=None):
    """Mock de Session: roteia query(Model) → objects[Model.__name__] (first/all)."""
    objects = objects or {}
    db = MagicMock()

    def _query(model_class):
        q = MagicMock()
        name = getattr(model_class, "__name__", str(model_class))
        obj = objects.get(name)
        q.filter.return_value.first.return_value = obj
        q.filter.return_value.all.return_value = [obj] if obj else []
        q.filter.return_value.order_by.return_value.all.return_value = (
            [obj] if obj else []
        )
        return q

    db.query.side_effect = _query
    return db


def _track_adds(db):
    added = []
    db.add.side_effect = lambda obj: added.append(obj)
    return added


# ─── 1. Custo médio ponderado ─────────────────────────────────────────────────

class TestAvgCost:
    def test_weighted_average_10_at_5_plus_5_at_7(self):
        """10 un @ R$5 + 5 un @ R$7 → avg_cost = R$5,67."""
        avg1 = compute_avg_cost(Decimal("0"), None, Decimal("10"), Decimal("5.00"))
        assert avg1 == Decimal("5.00")
        avg2 = compute_avg_cost(Decimal("10"), avg1, Decimal("5"), Decimal("7.00"))
        assert avg2 == Decimal("5.67")

    def test_receive_order_recalculates_avg_cost_and_stock(self):
        """receive_order incrementa stock e recalcula avg_cost no produto."""
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=10, avg_cost=Decimal("5.00"))
        db = _make_db({"Product": product})

        stock_service.receive_order(
            company_id=company_id,
            supplier_id=None,
            items=[{"product_id": product.id, "quantity": 5, "unit_cost": "7.00"}],
            created_by=uuid.uuid4(),
            db=db,
        )

        assert product.avg_cost == Decimal("5.67")
        assert product.stock == 15
        assert db.commit.call_count == 1


# ─── 2. receive_order → Payable sem Entry CUSTO (Financial-1) ─────────────────

class TestReceiveOrderFinancial1:
    def test_creates_payable_without_entry_and_without_movement(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=0, avg_cost=None)
        db = _make_db({"Product": product})
        added = _track_adds(db)

        order, payable = stock_service.receive_order(
            company_id=company_id,
            supplier_id=None,
            items=[{"product_id": product.id, "quantity": 10, "unit_cost": "5.00"}],
            created_by=uuid.uuid4(),
            db=db,
        )

        payables = [o for o in added if isinstance(o, Payable)]
        installments = [o for o in added if isinstance(o, PayableInstallment)]
        stock_movements = [o for o in added if isinstance(o, StockMovement)]
        entries = [o for o in added if isinstance(o, Entry)]
        movements = [o for o in added if isinstance(o, Movement)]

        assert len(payables) == 1
        assert payables[0].status == "OPEN"
        assert payables[0].source_type == "STOCK_PURCHASE"
        assert payables[0].total_amount == Decimal("50.00")
        assert len(installments) == 1  # CASH_AT_CREATION → 1 parcela
        assert len(stock_movements) == 1
        assert stock_movements[0].movement_type == "ENTRADA"
        assert stock_movements[0].unit_cost == Decimal("5.00")
        # Financial-1: receber ≠ reconhecer custo — sem Entry, sem Movement
        assert entries == []
        assert movements == []

    def test_installments_sum_must_match_total(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id)
        db = _make_db({"Product": product})

        with pytest.raises(HTTPException) as exc:
            stock_service.receive_order(
                company_id=company_id,
                supplier_id=None,
                items=[{"product_id": product.id, "quantity": 10, "unit_cost": "5.00"}],
                created_by=uuid.uuid4(),
                db=db,
                closing_method="INSTALLMENTS",
                installments=[{"amount": "20.00", "due_date": date(2026, 7, 1)}],
            )
        assert exc.value.status_code == 422


# ─── 3. record_movement VENDA → Entry CUSTO sem Movement ──────────────────────

class TestRecordMovementFinancial1:
    def test_venda_creates_entry_custo_without_movement(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=10, avg_cost=Decimal("5.67"))
        db = _make_db({"Product": product, "TenantConfig": _make_tenant_config()})
        added = _track_adds(db)

        stock_service.record_movement(
            company_id=company_id,
            product_id=product.id,
            movement_type="VENDA",
            quantity=2,
            created_by=uuid.uuid4(),
            db=db,
        )

        entries = [o for o in added if isinstance(o, Entry)]
        movements = [o for o in added if isinstance(o, Movement)]

        assert len(entries) == 1
        assert entries[0].type == "CUSTO"
        assert entries[0].category == "PRODUTO_VENDIDO"
        assert entries[0].direction == "SUBTRACTS"
        assert entries[0].amount == Decimal("11.34")  # 2 × 5,67 (avg_cost)
        assert entries[0].movement_id is None
        # Financial-1: cash flow foi na compra — sem Movement aqui
        assert movements == []
        assert product.stock == 8

    def test_uso_interno_and_perda_categories(self):
        company_id = uuid.uuid4()
        for movement_type, category in (
            ("USO_INTERNO", "INSUMOS_USO_INTERNO"),
            ("PERDA", "PERDA_ESTOQUE"),
        ):
            product = _make_product(company_id=company_id, stock=5, avg_cost=Decimal("4.00"))
            db = _make_db({"Product": product, "TenantConfig": _make_tenant_config()})
            added = _track_adds(db)

            stock_service.record_movement(
                company_id=company_id,
                product_id=product.id,
                movement_type=movement_type,
                quantity=1,
                created_by=uuid.uuid4(),
                db=db,
            )

            entries = [o for o in added if isinstance(o, Entry)]
            assert len(entries) == 1
            assert entries[0].category == category

    def test_ajuste_creates_entry_contagem_estoque_with_audit(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=10, avg_cost=Decimal("5.00"))
        db = _make_db({"Product": product, "TenantConfig": _make_tenant_config()})
        added = _track_adds(db)

        with patch.object(stock_service, "record_sensitive_action") as audit:
            stock_service.record_movement(
                company_id=company_id,
                product_id=product.id,
                movement_type="AJUSTE",
                quantity=-2,
                created_by=uuid.uuid4(),
                db=db,
                notes="Contagem física divergente",
            )

        entries = [o for o in added if isinstance(o, Entry)]
        assert len(entries) == 1
        assert entries[0].category == "CONTAGEM_ESTOQUE"
        assert entries[0].type == "AJUSTE"
        assert entries[0].direction == "SUBTRACTS"
        assert audit.called
        assert product.stock == 8


# ─── 4. AJUSTE sem notes → 422 ────────────────────────────────────────────────

class TestAjusteRequiresNotes:
    def test_ajuste_without_notes_raises_422(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=10)
        db = _make_db({"Product": product, "TenantConfig": _make_tenant_config()})

        with pytest.raises(HTTPException) as exc:
            stock_service.record_movement(
                company_id=company_id,
                product_id=product.id,
                movement_type="AJUSTE",
                quantity=-1,
                created_by=uuid.uuid4(),
                db=db,
                notes=None,
            )
        assert exc.value.status_code == 422
        assert not db.commit.called


# ─── 5. pay_installment atômico ───────────────────────────────────────────────

class TestPayInstallmentAtomic:
    def test_movement_failure_persists_nothing(self):
        """Falha ao criar o Movement → exceção propaga, nada commitado."""
        company_id = uuid.uuid4()
        payable = _make_payable(company_id=company_id)
        installment = _make_installment(payable.id, company_id)
        db = _make_db({"Payable": payable, "PayableInstallment": installment})

        with patch.object(
            payables_service,
            "handle_payable_installment_paid",
            side_effect=HTTPException(status_code=422, detail="sem conta padrão"),
        ):
            with pytest.raises(HTTPException):
                payables_service.pay_installment(
                    payable_id=payable.id,
                    installment_id=installment.id,
                    company_id=company_id,
                    db=db,
                )

        assert not db.commit.called
        assert installment.status == "OPEN"
        assert payable.status == "OPEN"

    def test_pay_creates_movement_outflow_without_entry(self):
        """Financial-1: pagar parcela cria Movement OUTFLOW sem Entry."""
        company_id = uuid.uuid4()
        account = _make_account(company_id)
        payable = _make_payable(company_id=company_id, total_amount=Decimal("50.00"))
        installment = _make_installment(payable.id, company_id, amount=Decimal("50.00"))
        db = _make_db({
            "Payable": payable,
            "PayableInstallment": installment,
            "Account": account,
        })
        added = _track_adds(db)

        result = payables_service.pay_installment(
            payable_id=payable.id,
            installment_id=installment.id,
            company_id=company_id,
            db=db,
        )

        movements = [o for o in added if isinstance(o, Movement)]
        entries = [o for o in added if isinstance(o, Entry)]
        assert len(movements) == 1
        assert movements[0].type == "OUTFLOW"
        assert movements[0].amount == Decimal("50.00")
        assert movements[0].source_type == "payable_installment"
        assert entries == []
        assert installment.status == "PAID"
        assert result.status == "PAID"
        assert db.commit.call_count == 1


# ─── 6. PARTIALLY_PAID → PAID com 2 parcelas ──────────────────────────────────

class TestPayableLifecycle:
    def test_two_installments_paid_in_sequence(self):
        company_id = uuid.uuid4()
        account = _make_account(company_id)
        payable = _make_payable(company_id=company_id, total_amount=Decimal("100.00"))
        inst1 = _make_installment(payable.id, company_id, amount=Decimal("50.00"), number=1)
        inst2 = _make_installment(payable.id, company_id, amount=Decimal("50.00"), number=2)

        db1 = _make_db({"Payable": payable, "PayableInstallment": inst1, "Account": account})
        payables_service.pay_installment(
            payable_id=payable.id, installment_id=inst1.id,
            company_id=company_id, db=db1,
        )
        assert payable.status == "PARTIALLY_PAID"
        assert payable.paid_amount == Decimal("50.00")

        db2 = _make_db({"Payable": payable, "PayableInstallment": inst2, "Account": account})
        payables_service.pay_installment(
            payable_id=payable.id, installment_id=inst2.id,
            company_id=company_id, db=db2,
        )
        assert payable.status == "PAID"
        assert payable.paid_amount == Decimal("100.00")

    def test_paid_installment_cannot_be_paid_again(self):
        company_id = uuid.uuid4()
        payable = _make_payable(company_id=company_id, status="PARTIALLY_PAID",
                                paid_amount=Decimal("50.00"))
        inst = _make_installment(payable.id, company_id)
        inst.status = "PAID"
        db = _make_db({"Payable": payable, "PayableInstallment": inst})

        with pytest.raises(HTTPException) as exc:
            payables_service.pay_installment(
                payable_id=payable.id, installment_id=inst.id,
                company_id=company_id, db=db,
            )
        assert exc.value.status_code == 422

    def test_cancel_paid_payable_rejected(self):
        company_id = uuid.uuid4()
        payable = _make_payable(company_id=company_id, status="PAID")
        db = _make_db({"Payable": payable})

        with pytest.raises(HTTPException) as exc:
            payables_service.cancel_payable(
                payable_id=payable.id, company_id=company_id,
                reason="qualquer", db=db,
            )
        assert exc.value.status_code == 422

    def test_cancel_partially_paid_requires_audit(self):
        company_id = uuid.uuid4()
        payable = _make_payable(company_id=company_id, status="PARTIALLY_PAID",
                                paid_amount=Decimal("50.00"))
        db = _make_db({"Payable": payable})

        with patch.object(payables_service, "record_sensitive_action") as audit:
            result = payables_service.cancel_payable(
                payable_id=payable.id, company_id=company_id,
                reason="Pedido devolvido ao fornecedor", db=db,
                actor_id=uuid.uuid4(),
            )
        assert audit.called
        assert result.status == "CANCELLED"


# ─── 7. Estoque zerado com controle ativo → 422 ───────────────────────────────

class TestNegativeStockControl:
    def test_venda_with_zero_stock_rejected_when_controlled(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=0, avg_cost=Decimal("5.00"))
        db = _make_db({
            "Product": product,
            "TenantConfig": _make_tenant_config(allow_negative_stock=False),
        })

        with pytest.raises(HTTPException) as exc:
            stock_service.record_movement(
                company_id=company_id,
                product_id=product.id,
                movement_type="VENDA",
                quantity=1,
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422
        assert not db.commit.called
        assert product.stock == 0

    def test_venda_allowed_when_tenant_opts_in_negative_stock(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=0, avg_cost=Decimal("5.00"))
        db = _make_db({
            "Product": product,
            "TenantConfig": _make_tenant_config(allow_negative_stock=True),
        })

        stock_service.record_movement(
            company_id=company_id,
            product_id=product.id,
            movement_type="VENDA",
            quantity=1,
            created_by=uuid.uuid4(),
            db=db,
        )
        assert product.stock == -1

    def test_missing_tenant_config_defaults_to_controlled(self):
        company_id = uuid.uuid4()
        product = _make_product(company_id=company_id, stock=0, avg_cost=Decimal("5.00"))
        db = _make_db({"Product": product})  # sem TenantConfig

        with pytest.raises(HTTPException) as exc:
            stock_service.record_movement(
                company_id=company_id,
                product_id=product.id,
                movement_type="VENDA",
                quantity=1,
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422


# ─── 8. DRE: Entry CUSTO em aggregate_dre ─────────────────────────────────────

class TestDreWithCusto:
    def test_custo_entries_aggregate_in_dre(self):
        company_id = uuid.uuid4()

        e1 = MagicMock()
        e1.type, e1.category, e1.amount = "CUSTO", "PRODUTO_VENDIDO", Decimal("11.34")
        e2 = MagicMock()
        e2.type, e2.category, e2.amount = "CUSTO", "PERDA_ESTOQUE", Decimal("5.67")
        e3 = MagicMock()
        e3.type, e3.category, e3.amount = "RECEITA", "PRODUTOS", Decimal("40.00")

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [e1, e2, e3]

        dre = financial_core.aggregate_dre(
            company_id=company_id,
            date_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 6, 30, tzinfo=timezone.utc),
            db=db,
        )

        assert dre["custo"]["PRODUTO_VENDIDO"] == Decimal("11.34")
        assert dre["custo"]["PERDA_ESTOQUE"] == Decimal("5.67")
        assert dre["custo_total"] == Decimal("17.01")
        assert dre["resultado_bruto"] == Decimal("22.99")  # 40,00 − 17,01


# ─── 9. stock_min_alert → evento publicado ────────────────────────────────────

class TestStockAlertWorker:
    def test_low_stock_publishes_event(self):
        from app.workers.tasks import stock_alert as stock_alert_module

        product = _make_product(stock=2, stock_min_alert=Decimal("5"))
        db = MagicMock()
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = [product]

        published = []
        worker = getattr(
            stock_alert_module.stock_alert_worker, "run",
            stock_alert_module.stock_alert_worker,
        )

        with patch.object(stock_alert_module, "SessionLocal", return_value=db), \
             patch("app.core.db_rls.set_rls_context"), \
             patch("app.core.idempotency.is_processed", return_value=False), \
             patch("app.core.idempotency.mark_processed"), \
             patch("app.infrastructure.event_bus.event_bus.publish",
                   side_effect=lambda e: published.append(e)):
            worker(MagicMock())

        assert len(published) == 1
        event = published[0]
        assert event.event_type == "stock.low_alert"
        assert event.idempotency_key.startswith(f"stock.low_alert:{product.id}:")
        assert event.payload["stock"] == 2

    def test_already_processed_today_not_republished(self):
        from app.workers.tasks import stock_alert as stock_alert_module

        product = _make_product(stock=2, stock_min_alert=Decimal("5"))
        db = MagicMock()
        db.query.return_value.filter.return_value.limit.return_value.all.return_value = [product]

        published = []
        worker = getattr(
            stock_alert_module.stock_alert_worker, "run",
            stock_alert_module.stock_alert_worker,
        )

        with patch.object(stock_alert_module, "SessionLocal", return_value=db), \
             patch("app.core.db_rls.set_rls_context"), \
             patch("app.core.idempotency.is_processed", return_value=True), \
             patch("app.infrastructure.event_bus.event_bus.publish",
                   side_effect=lambda e: published.append(e)):
            worker(MagicMock())

        assert published == []


# ─── 10. FK expenses.supplier_id → suppliers ──────────────────────────────────

class TestExpensesSupplierFk:
    def test_migration_adds_fk_constraint(self):
        migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / (
            "e0s17a_stock_suppliers_payables.py"
        )
        content = migration.read_text(encoding="utf-8")
        assert "fk_expenses_supplier" in content
        assert "FOREIGN KEY (supplier_id) REFERENCES suppliers(id)" in content
        assert "ON DELETE SET NULL" in content
        assert 'down_revision: Union[str, Sequence[str], None] = "e0s_rls_fix_fase2"' in content

    def test_rls_canonical_on_all_new_tables(self):
        migration = Path(__file__).resolve().parents[1] / "migrations" / "versions" / (
            "e0s17a_stock_suppliers_payables.py"
        )
        content = migration.read_text(encoding="utf-8")
        for table in ("suppliers", "supplier_orders", "stock_movements",
                      "payables", "payable_installments"):
            assert f"CREATE TABLE IF NOT EXISTS {table}" in content
        assert "app.current_company_id" in content
        assert "app.company_id'" not in content  # padrão antigo proibido


# ─── 11. Cross-tenant ─────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_product_of_company_a_invisible_to_company_b(self):
        db = _make_db({})  # query com company_id de B não encontra o produto de A

        with pytest.raises(HTTPException) as exc:
            stock_service.record_movement(
                company_id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                movement_type="VENDA",
                quantity=1,
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 404

    def test_payable_of_company_a_invisible_to_company_b(self):
        db = _make_db({})

        with pytest.raises(HTTPException) as exc:
            payables_service.pay_installment(
                payable_id=uuid.uuid4(),
                installment_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 404

    def test_supplier_of_company_a_invisible_to_company_b(self):
        from app.modules.suppliers import service as suppliers_service

        db = _make_db({})
        with pytest.raises(HTTPException) as exc:
            suppliers_service.get_supplier(uuid.uuid4(), uuid.uuid4(), db)
        assert exc.value.status_code == 404


# ─── Extras: validações de domínio ────────────────────────────────────────────

class TestDomainValidations:
    def test_entrada_not_allowed_via_record_movement(self):
        db = _make_db({})
        with pytest.raises(HTTPException) as exc:
            stock_service.record_movement(
                company_id=uuid.uuid4(),
                product_id=uuid.uuid4(),
                movement_type="ENTRADA",
                quantity=1,
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422

    def test_handle_stock_cost_entry_rejects_non_cost_category(self):
        db = MagicMock()
        with pytest.raises(HTTPException) as exc:
            financial_core.handle_stock_cost_entry(
                movement_id=uuid.uuid4(),
                amount=Decimal("10.00"),
                category="ALUGUEL",  # DESPESA — não é custo de estoque
                company_id=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422

    def test_deactivate_supplier_is_soft_delete(self):
        from app.modules.suppliers import service as suppliers_service

        supplier = MagicMock()
        supplier.active = True
        db = _make_db({"Supplier": supplier})

        result = suppliers_service.deactivate_supplier(uuid.uuid4(), uuid.uuid4(), db)
        assert result.active is False
        assert not db.delete.called
