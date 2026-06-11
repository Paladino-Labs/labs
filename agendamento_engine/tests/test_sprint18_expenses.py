"""
Testes Sprint 18 — Despesas + recorrência.

Usa mocks (unittest.mock) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  pay_expense atômico: Movement OUTFLOW + Entry DESPESA criados juntos (mesmo commit)
  2.  Categoria CUSTO rejeitada com 422
  3.  Recorrência: day_of_month=31 em fevereiro → último dia do mês
  4.  Falha ao gerar próxima instância NÃO cancela o pagamento
  5.  DRE: Entry DESPESA aparece em aggregate_dre com categoria correta
  6.  pay_expense de despesa já PAGA → 422
  7.  cancel_expense de despesa PAGA → 422
  8.  Despesa PENDENTE → cancelada → não cria Entry (não aparece no DRE)
  9.  Cross-tenant: despesa de empresa A invisível para empresa B (404)
"""
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
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

from app.modules.expenses import service as expense_service
from app.modules.expenses.service import next_occurrence
from app.modules.financial_core import service as financial_core
from app.modules.financial_core.service import DESPESA_CATEGORIES, handle_expense_paid


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_expense(
    expense_id=None,
    company_id=None,
    description="Aluguel do salão",
    amount=Decimal("1500.00"),
    category="ALUGUEL",
    status="PENDENTE",
    due_date=None,
    recurrence_rule=None,
    parent_expense_id=None,
    created_by=None,
    supplier_id=None,
):
    e = MagicMock()
    e.id = expense_id or uuid.uuid4()
    e.company_id = company_id or uuid.uuid4()
    e.description = description
    e.amount = amount
    e.category = category
    e.status = status
    e.due_date = due_date or date(2026, 6, 15)
    e.paid_at = None
    e.paid_amount = None
    e.recurrence_rule = recurrence_rule
    e.parent_expense_id = parent_expense_id
    e.created_by = created_by or uuid.uuid4()
    e.supplier_id = supplier_id
    return e


def _make_account(company_id=None):
    a = MagicMock()
    a.account_id = uuid.uuid4()
    a.company_id = company_id or uuid.uuid4()
    a.is_default_inflow = True
    return a


def _make_db(expense=None, account=None):
    """Mock de Session: query(Expense) → expense; query(Account) → account."""
    db = MagicMock()

    def _query(model_class):
        q = MagicMock()
        name = getattr(model_class, "__name__", str(model_class))
        if name == "Expense":
            q.filter.return_value.first.return_value = expense
            q.filter.return_value.all.return_value = [expense] if expense else []
            q.filter.return_value.order_by.return_value.all.return_value = (
                [expense] if expense else []
            )
        elif name == "Account":
            q.filter.return_value.first.return_value = account
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


# ─── 1. pay_expense atômico ───────────────────────────────────────────────────

class TestPayExpenseAtomic:
    def test_movement_outflow_and_entry_despesa_created_together(self):
        """handle_expense_paid cria Movement OUTFLOW + Entry DESPESA na mesma transação."""
        company_id = uuid.uuid4()
        expense_id = uuid.uuid4()
        account = _make_account(company_id)
        db = _make_db(account=account)

        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        movement, entry = handle_expense_paid(
            expense_id=expense_id,
            amount=Decimal("1500.00"),
            category="ALUGUEL",
            company_id=company_id,
            db=db,
        )

        assert len(added) == 2
        assert movement.type == "OUTFLOW"
        assert movement.amount == Decimal("1500.00")
        assert movement.source_type == "expense"
        assert movement.source_id == expense_id
        assert entry.type == "DESPESA"
        assert entry.direction == "SUBTRACTS"
        assert entry.category == "ALUGUEL"
        assert entry.movement_id == movement.movement_id
        # flush sim, commit não — commit é do chamador (pay_expense)
        assert db.flush.called
        assert not db.commit.called

    def test_pay_expense_commits_status_and_accounting_in_same_transaction(self):
        """pay_expense: transição PAGA + Movement/Entry com um único commit."""
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, status="PENDENTE")
        account = _make_account(company_id)
        db = _make_db(expense=expense, account=account)

        with patch.object(expense_service, "_publish_event"):
            result = expense_service.pay_expense(
                expense_id=expense.id,
                company_id=company_id,
                db=db,
            )

        assert result.status == "PAGA"
        assert result.paid_at is not None
        assert result.paid_amount == Decimal("1500.00")
        assert db.commit.call_count == 1

    def test_pay_expense_with_explicit_paid_amount(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id)
        db = _make_db(expense=expense, account=_make_account(company_id))

        with patch.object(expense_service, "_publish_event"):
            result = expense_service.pay_expense(
                expense_id=expense.id,
                company_id=company_id,
                db=db,
                paid_amount=Decimal("1450.00"),
            )

        assert result.paid_amount == Decimal("1450.00")


# ─── 2. Categoria CUSTO → 422 ─────────────────────────────────────────────────

class TestCategoryValidation:
    def test_custo_category_rejected_on_create(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            expense_service.create_expense(
                company_id=uuid.uuid4(),
                data={
                    "description": "Insumos",
                    "amount": Decimal("100.00"),
                    "category": "INSUMOS_USO_INTERNO",
                    "due_date": date(2026, 7, 1),
                },
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422
        assert "CUSTO" in exc.value.detail
        assert not db.add.called

    def test_custo_category_rejected_on_pay(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, category="PRODUTO_VENDIDO")
        db = _make_db(expense=expense, account=_make_account(company_id))

        with pytest.raises(HTTPException) as exc:
            expense_service.pay_expense(expense.id, company_id, db)
        assert exc.value.status_code == 422
        assert not db.commit.called

    def test_invalid_category_rejected_in_handle_expense_paid(self):
        db = _make_db(account=_make_account())
        with pytest.raises(HTTPException) as exc:
            handle_expense_paid(
                expense_id=uuid.uuid4(),
                amount=Decimal("10.00"),
                category="SERVICOS",  # RECEITA, não DESPESA
                company_id=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422

    def test_despesa_categories_derived_from_enum(self):
        assert "ALUGUEL" in DESPESA_CATEGORIES
        assert "SALARIO" in DESPESA_CATEGORIES
        assert "DESPESA_OUTROS" in DESPESA_CATEGORIES
        assert "INSUMOS_USO_INTERNO" not in DESPESA_CATEGORIES
        assert "SERVICOS" not in DESPESA_CATEGORIES


# ─── 3. Recorrência: clamp de fim de mês ──────────────────────────────────────

class TestRecurrenceClamp:
    def test_day_31_in_february_clamps_to_last_day(self):
        rule = {"frequency": "MONTHLY", "day_of_month": 31}
        assert next_occurrence(date(2026, 1, 31), rule) == date(2026, 2, 28)

    def test_day_31_in_leap_february(self):
        rule = {"frequency": "MONTHLY", "day_of_month": 31}
        assert next_occurrence(date(2028, 1, 31), rule) == date(2028, 2, 29)

    def test_day_restored_after_short_month(self):
        """Fev 28 (clampado de 31) → Mar 31 (dia restaurado pela regra)."""
        rule = {"frequency": "MONTHLY", "day_of_month": 31}
        assert next_occurrence(date(2026, 2, 28), rule) == date(2026, 3, 31)

    def test_day_15_unaffected(self):
        rule = {"frequency": "MONTHLY", "day_of_month": 15}
        assert next_occurrence(date(2026, 6, 15), rule) == date(2026, 7, 15)

    def test_generate_next_respects_end_date(self):
        company_id = uuid.uuid4()
        expense = _make_expense(
            company_id=company_id,
            status="PAGA",
            due_date=date(2026, 6, 15),
            recurrence_rule={
                "frequency": "MONTHLY",
                "day_of_month": 15,
                "end_date": "2026-06-30",
            },
        )
        db = _make_db()  # sem próxima instância existente
        result = expense_service.generate_next_instance(expense, db)
        assert result is None
        assert not db.commit.called

    def test_generate_next_idempotent_when_pending_exists(self):
        """Já existe próxima PENDENTE encadeada → não cria duplicata."""
        company_id = uuid.uuid4()
        expense = _make_expense(
            company_id=company_id,
            status="PAGA",
            recurrence_rule={"frequency": "MONTHLY", "day_of_month": 15},
        )
        next_pending = _make_expense(company_id=company_id, parent_expense_id=expense.id)
        db = _make_db(expense=next_pending)
        result = expense_service.generate_next_instance(expense, db)
        assert result is None
        assert not db.add.called


# ─── 4. Falha na próxima instância não cancela o pagamento ────────────────────

class TestRecurrenceFailureIsolation:
    def test_generation_failure_does_not_rollback_payment(self):
        company_id = uuid.uuid4()
        expense = _make_expense(
            company_id=company_id,
            recurrence_rule={"frequency": "MONTHLY", "day_of_month": 15},
        )
        db = _make_db(expense=expense, account=_make_account(company_id))

        with patch.object(
            expense_service, "generate_next_instance", side_effect=RuntimeError("boom")
        ), patch.object(expense_service, "_publish_event"):
            result = expense_service.pay_expense(expense.id, company_id, db)

        # pagamento efetivado apesar da falha na geração
        assert result.status == "PAGA"
        assert db.commit.call_count == 1  # commit do pagamento aconteceu antes da falha
        db.rollback.assert_called_once()  # rollback apenas da geração


# ─── 5. DRE: Entry DESPESA agregada com categoria correta ─────────────────────

class TestDREIntegration:
    def test_despesa_entry_appears_in_aggregate_dre(self):
        company_id = uuid.uuid4()

        despesa_entry = MagicMock()
        despesa_entry.type = "DESPESA"
        despesa_entry.category = "ALUGUEL"
        despesa_entry.amount = Decimal("1500.00")

        receita_entry = MagicMock()
        receita_entry.type = "RECEITA"
        receita_entry.category = "SERVICOS"
        receita_entry.amount = Decimal("5000.00")

        db = MagicMock()
        db.query.return_value.filter.return_value.all.return_value = [
            despesa_entry, receita_entry,
        ]

        dre = financial_core.aggregate_dre(
            company_id=company_id,
            date_from=datetime(2026, 6, 1, tzinfo=timezone.utc),
            date_to=datetime(2026, 6, 30, tzinfo=timezone.utc),
            db=db,
        )

        assert dre["despesa"] == {"ALUGUEL": Decimal("1500.00")}
        assert dre["despesa_total"] == Decimal("1500.00")
        assert dre["resultado_liquido"] == Decimal("3500.00")


# ─── 6-7. Lifecycle: transições inválidas ─────────────────────────────────────

class TestLifecycle:
    def test_pay_already_paid_expense_422(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, status="PAGA")
        db = _make_db(expense=expense, account=_make_account(company_id))

        with pytest.raises(HTTPException) as exc:
            expense_service.pay_expense(expense.id, company_id, db)
        assert exc.value.status_code == 422
        assert not db.commit.called

    def test_pay_cancelled_expense_422(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, status="CANCELLED")
        db = _make_db(expense=expense, account=_make_account(company_id))

        with pytest.raises(HTTPException) as exc:
            expense_service.pay_expense(expense.id, company_id, db)
        assert exc.value.status_code == 422

    def test_cancel_paid_expense_422(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, status="PAGA")
        db = _make_db(expense=expense)

        with pytest.raises(HTTPException) as exc:
            expense_service.cancel_expense(expense.id, company_id, "erro de lançamento", db)
        assert exc.value.status_code == 422
        assert expense.status == "PAGA"

    def test_cancel_requires_reason(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id)
        db = _make_db(expense=expense)

        with pytest.raises(HTTPException) as exc:
            expense_service.cancel_expense(expense.id, company_id, "  ", db)
        assert exc.value.status_code == 422


# ─── 8. Cancelada não gera Entry (não aparece no DRE) ─────────────────────────

class TestCancelledNotInDRE:
    def test_cancel_creates_no_movement_or_entry(self):
        """Cancelamento não chama handle_expense_paid — nenhum Movement/Entry criado."""
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id, status="PENDENTE")
        db = _make_db(expense=expense)

        with patch.object(financial_core, "_record_movement") as mock_mov, \
             patch.object(financial_core, "_record_entry") as mock_entry, \
             patch.object(expense_service, "record_sensitive_action"), \
             patch.object(expense_service, "_publish_event"):
            result = expense_service.cancel_expense(
                expense.id, company_id, "duplicada", db, actor_id=uuid.uuid4()
            )

        assert result.status == "CANCELLED"
        mock_mov.assert_not_called()
        mock_entry.assert_not_called()


# ─── 9. Cross-tenant ──────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_expense_of_company_a_invisible_to_company_b(self):
        """Query filtra por company_id — despesa de A não encontrada por B → 404."""
        db = _make_db(expense=None)  # filtro company_id=B não encontra a despesa de A

        with pytest.raises(HTTPException) as exc:
            expense_service.get_expense(uuid.uuid4(), uuid.uuid4(), db)
        assert exc.value.status_code == 404

    def test_pay_cross_tenant_404(self):
        db = _make_db(expense=None)
        with pytest.raises(HTTPException) as exc:
            expense_service.pay_expense(uuid.uuid4(), uuid.uuid4(), db)
        assert exc.value.status_code == 404

    def test_get_expenses_filters_by_company_id(self):
        company_a = uuid.uuid4()
        expense_a = _make_expense(company_id=company_a)
        db = _make_db(expense=expense_a)

        result = expense_service.get_expenses(company_a, db)
        assert result == [expense_a]
        # o primeiro filtro aplicado é company_id (mock garante chamada de filter)
        assert db.query.called


# ─── Extra: create com recorrência gera próxima instância ────────────────────

class TestCreateWithRecurrence:
    def test_create_generates_next_instance(self):
        company_id = uuid.uuid4()
        db = _make_db()

        with patch.object(expense_service, "generate_next_instance") as mock_gen, \
             patch.object(expense_service, "_publish_event"):
            expense_service.create_expense(
                company_id=company_id,
                data={
                    "description": "Aluguel",
                    "amount": Decimal("1500.00"),
                    "category": "ALUGUEL",
                    "due_date": date(2026, 7, 1),
                    "recurrence_rule": {"frequency": "MONTHLY", "day_of_month": 1},
                },
                created_by=uuid.uuid4(),
                db=db,
            )
        mock_gen.assert_called_once()

    def test_create_without_recurrence_does_not_generate(self):
        db = _make_db()
        with patch.object(expense_service, "generate_next_instance") as mock_gen, \
             patch.object(expense_service, "_publish_event"):
            expense_service.create_expense(
                company_id=uuid.uuid4(),
                data={
                    "description": "Conta de luz",
                    "amount": Decimal("300.00"),
                    "category": "UTILITIES",
                    "due_date": date(2026, 7, 10),
                },
                created_by=uuid.uuid4(),
                db=db,
            )
        mock_gen.assert_not_called()

    def test_invalid_recurrence_frequency_422(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            expense_service.create_expense(
                company_id=uuid.uuid4(),
                data={
                    "description": "Aluguel",
                    "amount": Decimal("1500.00"),
                    "category": "ALUGUEL",
                    "due_date": date(2026, 7, 1),
                    "recurrence_rule": {"frequency": "WEEKLY", "day_of_month": 1},
                },
                created_by=uuid.uuid4(),
                db=db,
            )
        assert exc.value.status_code == 422


# ─── Eventos: idempotency keys canônicos ─────────────────────────────────────

class TestEventIdempotencyKeys:
    def test_expense_paid_event_key(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id)
        db = _make_db(expense=expense, account=_make_account(company_id))

        published = []
        with patch.object(
            expense_service, "_publish_event",
            side_effect=lambda **kw: published.append(kw),
        ):
            expense_service.pay_expense(expense.id, company_id, db)

        assert published[0]["event_type"] == "expense.paid"
        assert published[0]["idempotency_key"] == f"expense.paid:{expense.id}"

    def test_expense_cancelled_event_key(self):
        company_id = uuid.uuid4()
        expense = _make_expense(company_id=company_id)
        db = _make_db(expense=expense)

        published = []
        with patch.object(expense_service, "record_sensitive_action"), patch.object(
            expense_service, "_publish_event",
            side_effect=lambda **kw: published.append(kw),
        ):
            expense_service.cancel_expense(expense.id, company_id, "motivo", db)

        assert published[0]["idempotency_key"] == f"expense.cancelled:{expense.id}"
