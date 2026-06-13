"""Contrato 6 — DRE correto (aggregate_dre).

Exercita handle_payment_confirmed / handle_stock_cost_entry / handle_expense_paid /
handle_commission_paid e verifica que as Entries aparecem no DRE com isolamento
por tenant e por período.
"""
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.infrastructure.db.models.entry import Entry
from app.modules.financial_core import service as fc


def _account(db, company_id):
    from app.infrastructure.db.models.account import Account
    acc = Account(company_id=company_id, name="CAIXA", type="CAIXA",
                  currency="BRL", is_default_inflow=True)
    db.add(acc)
    return acc


class TestDREContract:
    def test_receita_from_payment(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        fc.handle_payment_confirmed(
            payment_id=uuid.uuid4(), gross_amount=Decimal("100"),
            provider_fee=Decimal("3"), target_account_id=acc.account_id,
            fee_source="MAQUININHA_CREDIT_VISA_MASTER", company_id=cid, db=db,
        )
        db.commit()
        dre = fc.aggregate_dre(cid, _past(), _future(), db)
        assert dre["receita_total"] == Decimal("100")
        assert dre["taxa_total"] == Decimal("3")

    def test_custo_from_stock_movement(self, db):
        cid = uuid.uuid4()
        fc.handle_stock_cost_entry(
            movement_id=uuid.uuid4(), amount=Decimal("25"),
            category="PRODUTO_VENDIDO", company_id=cid, db=db,
        )
        db.commit()
        dre = fc.aggregate_dre(cid, _past(), _future(), db)
        assert dre["custo_total"] == Decimal("25")
        assert "PRODUTO_VENDIDO" in dre["custo"]

    def test_despesa_from_expense(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        fc.handle_expense_paid(
            expense_id=uuid.uuid4(), amount=Decimal("500"),
            category="ALUGUEL", account_id=acc.account_id,
            company_id=cid, db=db,
        )
        db.commit()
        dre = fc.aggregate_dre(cid, _past(), _future(), db)
        assert dre["despesa_total"] == Decimal("500")
        assert "ALUGUEL" in dre["despesa"]

    def test_comissao_payout(self, db):
        cid = uuid.uuid4()
        acc = _account(db, cid)
        fc.handle_commission_paid(
            payout_id=uuid.uuid4(), amount=Decimal("40"),
            account_id=acc.account_id, professional_id=uuid.uuid4(),
            company_id=cid, db=db,
        )
        db.commit()
        dre = fc.aggregate_dre(cid, _past(), _future(), db)
        assert dre["comissao_total"] == Decimal("40")

    def test_dre_period_filter(self, db):
        """Entries de fora do período não entram."""
        cid = uuid.uuid4()
        jan = Entry(company_id=cid, type="RECEITA", direction="ADDS",
                    amount=Decimal("10"), category="SERVICOS",
                    source_type="payment", source_id=uuid.uuid4(),
                    occurred_at=datetime(2026, 1, 15, tzinfo=timezone.utc))
        feb = Entry(company_id=cid, type="RECEITA", direction="ADDS",
                    amount=Decimal("99"), category="SERVICOS",
                    source_type="payment", source_id=uuid.uuid4(),
                    occurred_at=datetime(2026, 2, 15, tzinfo=timezone.utc))
        db.add(jan)
        db.add(feb)
        dre = fc.aggregate_dre(
            cid,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            datetime(2026, 1, 31, 23, 59, tzinfo=timezone.utc),
            db,
        )
        assert dre["receita_total"] == Decimal("10")

    def test_dre_cross_tenant_isolation(self, db):
        a, b = uuid.uuid4(), uuid.uuid4()
        acc_a, acc_b = _account(db, a), _account(db, b)
        fc.handle_payment_confirmed(
            payment_id=uuid.uuid4(), gross_amount=Decimal("100"),
            provider_fee=Decimal("0"), target_account_id=acc_a.account_id,
            fee_source=None, company_id=a, db=db)
        fc.handle_payment_confirmed(
            payment_id=uuid.uuid4(), gross_amount=Decimal("777"),
            provider_fee=Decimal("0"), target_account_id=acc_b.account_id,
            fee_source=None, company_id=b, db=db)
        db.commit()
        dre_a = fc.aggregate_dre(a, _past(), _future(), db)
        assert dre_a["receita_total"] == Decimal("100")  # não inclui B (777)


def _past():
    return datetime.now(timezone.utc) - timedelta(days=365)


def _future():
    return datetime.now(timezone.utc) + timedelta(days=365)
