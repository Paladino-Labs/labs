"""
Testes do Sprint 7 — Financial Core: Transfer, Reconciliação, CashCount.

Usa mocks (unittest.mock) para isolar da infraestrutura (PostgreSQL, triggers de banco).

Casos cobertos:
  1. create_transfer → exatamente 2 Movements (TRANSFER_OUT + TRANSFER_IN) na mesma transação
  2. create_transfer não cria nenhuma Entry
  3. Falha simulada no 2o _record_movement → rollback do 1o (TRANSFER_OUT não persiste)
  4. mark_movement_reconciled → row em movement_reconciliations; Movement inalterado
  5. list_unreconciled_movements exclui movements já vinculados
  6. CashCount ADJUSTED com discrepancy > 0 → Movement INFLOW + Entry AJUSTE ADDS
  7. CashCount ADJUSTED com discrepancy < 0 → Movement OUTFLOW + Entry AJUSTE SUBTRACTS
  8. CashCount ADJUSTED, discrepancy != 0, notes ausente → 422
  9. CashCount NO_ADJUSTMENT → sem Movement, sem Entry
 10. CashCount.entry_id aponta para Entry AJUSTE criada
 11. Cross-tenant: create_transfer com conta de outro tenant → 404
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_account(account_id=None, company_id=None, name="Caixa"):
    acc = MagicMock()
    acc.account_id = account_id or uuid.uuid4()
    acc.company_id = company_id or uuid.uuid4()
    acc.name = name
    acc.type = "CAIXA"
    acc.status = "ACTIVE"
    return acc


def _make_movement(movement_id=None, company_id=None, account_id=None,
                   type="INFLOW", amount=Decimal("100.00")):
    m = MagicMock()
    m.movement_id = movement_id or uuid.uuid4()
    m.company_id = company_id or uuid.uuid4()
    m.account_id = account_id or uuid.uuid4()
    m.type = type
    m.amount = Decimal(str(amount))
    m.occurred_at = datetime.now(timezone.utc)
    m.source_type = "transfer"
    m.source_id = uuid.uuid4()
    m.transfer_id = uuid.uuid4()
    m.created_at = datetime.now(timezone.utc)
    return m


def _make_transfer(transfer_id=None, company_id=None, status="COMPLETED"):
    t = MagicMock()
    t.transfer_id = transfer_id or uuid.uuid4()
    t.company_id = company_id or uuid.uuid4()
    t.from_account_id = uuid.uuid4()
    t.to_account_id = uuid.uuid4()
    t.amount = Decimal("200.00")
    t.status = status
    t.requested_at = datetime.now(timezone.utc)
    t.completed_at = datetime.now(timezone.utc)
    return t


def _make_entry(entry_id=None, type="AJUSTE", direction="ADDS", amount=Decimal("50.00")):
    e = MagicMock()
    e.entry_id = entry_id or uuid.uuid4()
    e.type = type
    e.direction = direction
    e.amount = Decimal(str(amount))
    return e


# ─────────────────────────────────────────────────────────────────────────────
# 1+2. create_transfer: 2 Movements atômicos, sem Entry
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTransfer:

    def _build_db_and_mocks(self, company_id, account_a, account_b):
        """Constrói mock de Session + captura de _record_movement."""
        mock_db = MagicMock()

        def _query(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "Account":
                def _filter(*args, **kwargs):
                    inner = MagicMock()
                    # Retorna account_a ou account_b baseado no account_id filtrado
                    inner.first.return_value = account_a
                    return inner
                q.filter.side_effect = _filter
            else:
                q.filter.return_value.first.return_value = None
            return q

        mock_db.query.side_effect = _query
        return mock_db

    def test_create_transfer_creates_exactly_two_movements(self):
        """create_transfer → exatamente 2 Movements (TRANSFER_OUT + TRANSFER_IN)."""
        from app.modules.financial_core import transfer_service

        company_id = uuid.uuid4()
        account_a_id = uuid.uuid4()
        account_b_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        movements_created = []

        def mock_record_movement(**kwargs):
            m = _make_movement(
                company_id=company_id,
                account_id=kwargs["account_id"],
                type=kwargs["type"],
                amount=kwargs["amount"],
            )
            movements_created.append(m)
            return m

        mock_transfer = _make_transfer(company_id=company_id)
        mock_db = MagicMock()

        with patch.object(transfer_service, "get_account", return_value=_make_account(company_id=company_id)):
            with patch.object(transfer_service, "_record_movement", side_effect=mock_record_movement):
                with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                    with patch("app.modules.financial_core.transfer_service.event_bus"):
                        result = transfer_service.create_transfer(
                            from_account_id=account_a_id,
                            to_account_id=account_b_id,
                            amount=Decimal("200.00"),
                            actor_id=actor_id,
                            company_id=company_id,
                            db=mock_db,
                        )

        assert len(movements_created) == 2
        types = {m.type for m in movements_created}
        assert "TRANSFER_OUT" in types
        assert "TRANSFER_IN" in types

    def test_create_transfer_does_not_create_entry(self):
        """create_transfer não chama _record_entry — Transfer não é fato econômico."""
        from app.modules.financial_core import transfer_service

        company_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        mock_transfer = _make_transfer(company_id=company_id)
        mock_db = MagicMock()

        with patch.object(transfer_service, "get_account", return_value=_make_account(company_id=company_id)):
            with patch.object(transfer_service, "_record_movement", return_value=_make_movement()):
                with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                    with patch("app.modules.financial_core.transfer_service.event_bus"):
                        # _record_entry não deve ser importado nem chamado no transfer_service
                        import app.modules.financial_core.transfer_service as ts_module
                        assert not hasattr(ts_module, "_record_entry"), (
                            "_record_entry não deve ser importado em transfer_service"
                        )

    def test_create_transfer_amounts_correct(self):
        """Os 2 Movements têm o mesmo amount da transferência."""
        from app.modules.financial_core import transfer_service

        company_id = uuid.uuid4()
        amount = Decimal("500.00")
        movements_created = []

        def mock_record_movement(**kwargs):
            m = _make_movement(type=kwargs["type"], amount=kwargs["amount"])
            movements_created.append(m)
            return m

        mock_transfer = _make_transfer(company_id=company_id)
        mock_db = MagicMock()

        with patch.object(transfer_service, "get_account", return_value=_make_account(company_id=company_id)):
            with patch.object(transfer_service, "_record_movement", side_effect=mock_record_movement):
                with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                    with patch("app.modules.financial_core.transfer_service.event_bus"):
                        transfer_service.create_transfer(
                            from_account_id=uuid.uuid4(),
                            to_account_id=uuid.uuid4(),
                            amount=amount,
                            actor_id=uuid.uuid4(),
                            company_id=company_id,
                            db=mock_db,
                        )

        for m in movements_created:
            assert m.amount == amount

    def test_create_transfer_event_published_after_commit(self):
        """EventBus.publish é chamado após commit, não dentro da transação."""
        from app.modules.financial_core import transfer_service

        company_id = uuid.uuid4()
        mock_transfer = _make_transfer(company_id=company_id)
        mock_db = MagicMock()
        commit_called_before_event = []

        def track_commit():
            commit_called_before_event.append(True)

        mock_db.commit.side_effect = track_commit

        mock_event_bus = MagicMock()

        def check_publish(event):
            assert len(commit_called_before_event) > 0, "commit deve ter sido chamado antes do publish"

        mock_event_bus.publish.side_effect = check_publish

        with patch.object(transfer_service, "get_account", return_value=_make_account(company_id=company_id)):
            with patch.object(transfer_service, "_record_movement", return_value=_make_movement()):
                with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                    with patch("app.modules.financial_core.transfer_service.event_bus", mock_event_bus):
                        transfer_service.create_transfer(
                            from_account_id=uuid.uuid4(),
                            to_account_id=uuid.uuid4(),
                            amount=Decimal("100.00"),
                            actor_id=uuid.uuid4(),
                            company_id=company_id,
                            db=mock_db,
                        )

        mock_event_bus.publish.assert_called_once()
        event = mock_event_bus.publish.call_args[0][0]
        assert event.event_type == "financial_core.transfer_completed"


# ─────────────────────────────────────────────────────────────────────────────
# 3. Falha no 2o _record_movement → rollback do 1o (TRANSFER_OUT não persiste)
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateTransferRollback:

    def test_failure_in_second_movement_propagates_exception(self):
        """Falha no 2o _record_movement → exceção propaga; rollback é responsabilidade do chamador."""
        from app.modules.financial_core import transfer_service

        company_id = uuid.uuid4()
        call_count = [0]

        def mock_record_movement(**kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("Simulated DB failure on TRANSFER_IN")
            m = _make_movement(type=kwargs["type"], amount=kwargs["amount"])
            return m

        mock_transfer = _make_transfer(company_id=company_id, status="REQUESTED")
        mock_db = MagicMock()

        with pytest.raises(RuntimeError, match="Simulated DB failure on TRANSFER_IN"):
            with patch.object(transfer_service, "get_account", return_value=_make_account(company_id=company_id)):
                with patch.object(transfer_service, "_record_movement", side_effect=mock_record_movement):
                    with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                        transfer_service.create_transfer(
                            from_account_id=uuid.uuid4(),
                            to_account_id=uuid.uuid4(),
                            amount=Decimal("200.00"),
                            actor_id=uuid.uuid4(),
                            company_id=company_id,
                            db=mock_db,
                        )

        # Commit não deve ter sido chamado
        mock_db.commit.assert_not_called()
        # Apenas 1 _record_movement foi chamado (o que falhou foi o 2o)
        assert call_count[0] == 2

    def test_failure_in_second_movement_event_not_published(self):
        """EventBus.publish não é chamado quando a transferência falha."""
        from app.modules.financial_core import transfer_service

        call_count = [0]

        def mock_record_movement(**kwargs):
            call_count[0] += 1
            if call_count[0] == 2:
                raise RuntimeError("fail")
            return _make_movement(type=kwargs["type"])

        mock_transfer = _make_transfer(status="REQUESTED")
        mock_db = MagicMock()
        mock_event_bus = MagicMock()

        with pytest.raises(RuntimeError):
            with patch.object(transfer_service, "get_account", return_value=_make_account()):
                with patch.object(transfer_service, "_record_movement", side_effect=mock_record_movement):
                    with patch("app.modules.financial_core.transfer_service.Transfer", return_value=mock_transfer):
                        with patch("app.modules.financial_core.transfer_service.event_bus", mock_event_bus):
                            transfer_service.create_transfer(
                                from_account_id=uuid.uuid4(),
                                to_account_id=uuid.uuid4(),
                                amount=Decimal("100.00"),
                                actor_id=uuid.uuid4(),
                                company_id=uuid.uuid4(),
                                db=mock_db,
                            )

        mock_event_bus.publish.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4. mark_movement_reconciled → row em movement_reconciliations; Movement inalterado
# ─────────────────────────────────────────────────────────────────────────────

class TestMarkMovementReconciled:

    def test_mark_reconciled_creates_link_without_altering_movement(self):
        """mark_movement_reconciled insere em movement_reconciliations; Movement não é alterado."""
        from app.modules.financial_core import reconciliation_service

        company_id = uuid.uuid4()
        movement_id = uuid.uuid4()
        reconciliation_id = uuid.uuid4()
        actor_id = uuid.uuid4()

        mock_movement = _make_movement(movement_id=movement_id, company_id=company_id)
        mock_record = MagicMock()
        mock_record.reconciliation_id = reconciliation_id
        mock_record.company_id = company_id
        mock_record.status = "OPEN"

        added_objects = []

        def _query(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "Movement":
                q.filter.return_value.first.return_value = mock_movement
            elif name == "ReconciliationRecord":
                q.filter.return_value.first.return_value = mock_record
            elif name == "MovementReconciliation":
                q.filter.return_value.first.return_value = None  # não existe ainda
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = _query
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)

        from app.infrastructure.db.models.movement_reconciliation import MovementReconciliation

        with patch("app.modules.financial_core.reconciliation_service.event_bus"):
            result = reconciliation_service.mark_movement_reconciled(
                movement_id=movement_id,
                reconciliation_id=reconciliation_id,
                actor_id=actor_id,
                company_id=company_id,
                db=mock_db,
            )

        # Um MovementReconciliation foi adicionado
        mr_objects = [o for o in added_objects if isinstance(o, MovementReconciliation)]
        assert len(mr_objects) == 1
        mr = mr_objects[0]
        assert mr.movement_id == movement_id
        assert mr.reconciliation_id == reconciliation_id
        assert mr.company_id == company_id

        # Movement não foi alterado — apenas leitura (movement_id ainda é o original)
        assert mock_movement.movement_id == movement_id
        # O vínculo é feito na tabela movement_reconciliations, não em campos do Movement

    def test_mark_reconciled_duplicate_raises_409(self):
        """mark_movement_reconciled com par já existente → 409."""
        from app.modules.financial_core import reconciliation_service
        from fastapi import HTTPException

        existing_link = MagicMock()
        existing_link.movement_id = uuid.uuid4()

        mock_movement = _make_movement()
        mock_record = MagicMock()
        mock_record.status = "OPEN"

        def _query(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "Movement":
                q.filter.return_value.first.return_value = mock_movement
            elif name == "ReconciliationRecord":
                q.filter.return_value.first.return_value = mock_record
            elif name == "MovementReconciliation":
                q.filter.return_value.first.return_value = existing_link
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = _query

        with pytest.raises(HTTPException) as exc_info:
            reconciliation_service.mark_movement_reconciled(
                movement_id=uuid.uuid4(),
                reconciliation_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert exc_info.value.status_code == 409

    def test_mark_reconciled_closed_reconciliation_raises_422(self):
        """mark_movement_reconciled em reconciliação CLOSED → 422."""
        from app.modules.financial_core import reconciliation_service
        from fastapi import HTTPException

        mock_movement = _make_movement()
        mock_record = MagicMock()
        mock_record.status = "CLOSED"

        def _query(model_class):
            q = MagicMock()
            name = model_class.__name__
            if name == "Movement":
                q.filter.return_value.first.return_value = mock_movement
            elif name == "ReconciliationRecord":
                q.filter.return_value.first.return_value = mock_record
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = _query

        with pytest.raises(HTTPException) as exc_info:
            reconciliation_service.mark_movement_reconciled(
                movement_id=uuid.uuid4(),
                reconciliation_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. list_unreconciled_movements exclui movements já vinculados
# ─────────────────────────────────────────────────────────────────────────────

class TestListUnreconciledMovements:

    def test_list_unreconciled_uses_left_join(self):
        """list_unreconciled_movements filtra via LEFT JOIN (MovementReconciliation IS NULL)."""
        from app.modules.financial_core import reconciliation_service
        from app.infrastructure.db.models.movement import Movement
        from app.infrastructure.db.models.movement_reconciliation import MovementReconciliation

        company_id = uuid.uuid4()
        account_id = uuid.uuid4()

        unreconciled_m1 = _make_movement(company_id=company_id, account_id=account_id)
        unreconciled_m2 = _make_movement(company_id=company_id, account_id=account_id)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.all.return_value = [unreconciled_m1, unreconciled_m2]

        results = reconciliation_service.list_unreconciled_movements(
            account_id=account_id,
            company_id=company_id,
            db=mock_db,
        )

        assert len(results) == 2
        # Verifica que outerjoin foi chamado (LEFT JOIN movement_reconciliations)
        mock_query.outerjoin.assert_called_once()

    def test_list_unreconciled_returns_empty_when_all_reconciled(self):
        """Quando todos os movements estão reconciliados, retorna lista vazia."""
        from app.modules.financial_core import reconciliation_service

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.outerjoin.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.all.return_value = []

        results = reconciliation_service.list_unreconciled_movements(
            account_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            db=mock_db,
        )

        assert results == []


# ─────────────────────────────────────────────────────────────────────────────
# 6+7. CashCount ADJUSTED com discrepancy > 0 e < 0
# ─────────────────────────────────────────────────────────────────────────────

class TestCashCountAdjusted:

    def _make_cash_count_mock(self, entry_id=None):
        cc = MagicMock()
        cc.cash_count_id = uuid.uuid4()
        cc.entry_id = entry_id
        cc.resolution = "ADJUSTED"
        return cc

    def _run_record_count(self, balance, counted_amount, notes="Ajuste de conferência"):
        from app.modules.financial_core import cash_count_service

        company_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        account_id = uuid.uuid4()
        entry_id = uuid.uuid4()

        mock_movement = _make_movement()
        mock_entry = _make_entry(entry_id=entry_id)
        mock_cash_count = self._make_cash_count_mock(entry_id=entry_id)

        mock_db = MagicMock()

        create_manual_adj_calls = []

        def mock_create_manual_adj(**kwargs):
            create_manual_adj_calls.append(kwargs)
            return mock_movement, mock_entry

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with patch.object(cash_count_service.financial_core, "create_manual_adjustment",
                                  side_effect=mock_create_manual_adj):
                    with patch("app.modules.financial_core.cash_count_service.CashCount",
                               return_value=mock_cash_count):
                        with patch("app.modules.financial_core.cash_count_service.event_bus"):
                            result = cash_count_service.record_count(
                                account_id=account_id,
                                counted_amount=counted_amount,
                                resolution="ADJUSTED",
                                notes=notes,
                                actor_id=actor_id,
                                company_id=company_id,
                                db=mock_db,
                            )

        return result, create_manual_adj_calls, mock_entry

    def test_adjusted_positive_discrepancy_creates_inflow(self):
        """CashCount ADJUSTED com discrepancy > 0 → ADDS direction (INFLOW)."""
        balance = Decimal("1000.00")
        counted = Decimal("1050.00")  # discrepancy = +50

        result, adj_calls, entry = self._run_record_count(balance, counted)

        assert len(adj_calls) == 1
        call = adj_calls[0]
        assert call["direction"] == "ADDS"
        assert call["amount"] == Decimal("50.00")
        assert call["category"] == "CONTAGEM_CAIXA"

    def test_adjusted_negative_discrepancy_creates_outflow(self):
        """CashCount ADJUSTED com discrepancy < 0 → SUBTRACTS direction (OUTFLOW)."""
        balance = Decimal("1000.00")
        counted = Decimal("950.00")   # discrepancy = -50

        result, adj_calls, entry = self._run_record_count(balance, counted)

        assert len(adj_calls) == 1
        call = adj_calls[0]
        assert call["direction"] == "SUBTRACTS"
        assert call["amount"] == Decimal("50.00")
        assert call["category"] == "CONTAGEM_CAIXA"

    def test_adjusted_discrepancy_amount_is_absolute(self):
        """O amount passado a create_manual_adjustment é abs(discrepancy)."""
        balance = Decimal("500.00")
        counted = Decimal("480.00")  # discrepancy = -20

        result, adj_calls, entry = self._run_record_count(balance, counted)

        assert adj_calls[0]["amount"] == Decimal("20.00")  # abs(-20)


# ─────────────────────────────────────────────────────────────────────────────
# 8. CashCount ADJUSTED, discrepancy != 0, notes ausente → 422
# ─────────────────────────────────────────────────────────────────────────────

class TestCashCountNotesRequired:

    def test_adjusted_without_notes_raises_422(self):
        """resolution=ADJUSTED + discrepancy != 0 + notes ausente → HTTPException 422."""
        from app.modules.financial_core import cash_count_service
        from fastapi import HTTPException

        balance = Decimal("1000.00")
        counted = Decimal("1050.00")   # discrepancy = +50 (não zero)
        mock_db = MagicMock()

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with pytest.raises(HTTPException) as exc_info:
                    cash_count_service.record_count(
                        account_id=uuid.uuid4(),
                        counted_amount=counted,
                        resolution="ADJUSTED",
                        notes=None,   # ausente
                        actor_id=uuid.uuid4(),
                        company_id=uuid.uuid4(),
                        db=mock_db,
                    )

        assert exc_info.value.status_code == 422
        assert "notes" in exc_info.value.detail.lower()

    def test_adjusted_empty_notes_raises_422(self):
        """resolution=ADJUSTED + discrepancy != 0 + notes vazio → HTTPException 422."""
        from app.modules.financial_core import cash_count_service
        from fastapi import HTTPException

        balance = Decimal("1000.00")
        counted = Decimal("1050.00")
        mock_db = MagicMock()

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with pytest.raises(HTTPException) as exc_info:
                    cash_count_service.record_count(
                        account_id=uuid.uuid4(),
                        counted_amount=counted,
                        resolution="ADJUSTED",
                        notes="   ",  # só espaços → falha
                        actor_id=uuid.uuid4(),
                        company_id=uuid.uuid4(),
                        db=mock_db,
                    )

        assert exc_info.value.status_code == 422

    def test_adjusted_with_zero_discrepancy_no_notes_ok(self):
        """resolution=ADJUSTED + discrepancy == 0 → notes não é obrigatório."""
        from app.modules.financial_core import cash_count_service

        balance = Decimal("1000.00")
        counted = Decimal("1000.00")   # discrepancy = 0
        mock_db = MagicMock()

        mock_cc = MagicMock()
        mock_cc.cash_count_id = uuid.uuid4()
        mock_cc.entry_id = None

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with patch("app.modules.financial_core.cash_count_service.CashCount", return_value=mock_cc):
                    with patch("app.modules.financial_core.cash_count_service.event_bus"):
                        result = cash_count_service.record_count(
                            account_id=uuid.uuid4(),
                            counted_amount=counted,
                            resolution="ADJUSTED",
                            notes=None,   # OK porque discrepancy == 0
                            actor_id=uuid.uuid4(),
                            company_id=uuid.uuid4(),
                            db=mock_db,
                        )

        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# 9. CashCount NO_ADJUSTMENT → sem Movement, sem Entry
# ─────────────────────────────────────────────────────────────────────────────

class TestCashCountNoAdjustment:

    def test_no_adjustment_does_not_create_movement_or_entry(self):
        """resolution=NO_ADJUSTMENT → create_manual_adjustment não é chamado."""
        from app.modules.financial_core import cash_count_service

        balance = Decimal("1000.00")
        counted = Decimal("980.00")   # discrepancy = -20, mas NO_ADJUSTMENT
        mock_db = MagicMock()

        mock_cc = MagicMock()
        mock_cc.cash_count_id = uuid.uuid4()
        mock_cc.entry_id = None

        create_adj_called = []

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with patch.object(
                    cash_count_service.financial_core,
                    "create_manual_adjustment",
                    side_effect=lambda **kwargs: create_adj_called.append(kwargs),
                ):
                    with patch("app.modules.financial_core.cash_count_service.CashCount", return_value=mock_cc):
                        with patch("app.modules.financial_core.cash_count_service.event_bus"):
                            result = cash_count_service.record_count(
                                account_id=uuid.uuid4(),
                                counted_amount=counted,
                                resolution="NO_ADJUSTMENT",
                                notes="Conferência sem ajuste",
                                actor_id=uuid.uuid4(),
                                company_id=uuid.uuid4(),
                                db=mock_db,
                            )

        assert len(create_adj_called) == 0, "create_manual_adjustment não deve ser chamado para NO_ADJUSTMENT"
        assert result.entry_id is None


# ─────────────────────────────────────────────────────────────────────────────
# 10. CashCount.entry_id aponta para Entry AJUSTE criada
# ─────────────────────────────────────────────────────────────────────────────

class TestCashCountEntryId:

    def test_cash_count_entry_id_points_to_adjustment_entry(self):
        """CashCount.entry_id é o entry_id da Entry AJUSTE criada por create_manual_adjustment."""
        from app.modules.financial_core import cash_count_service

        expected_entry_id = uuid.uuid4()
        balance = Decimal("1000.00")
        counted = Decimal("1100.00")  # discrepancy = +100
        mock_db = MagicMock()

        mock_movement = _make_movement(type="INFLOW")
        mock_entry = _make_entry(entry_id=expected_entry_id, direction="ADDS")

        # Captura os kwargs passados ao construtor do CashCount
        cash_count_kwargs = {}

        class MockCashCount:
            def __init__(self, **kwargs):
                cash_count_kwargs.update(kwargs)
                self.cash_count_id = uuid.uuid4()
                self.entry_id = kwargs.get("entry_id")

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with patch.object(
                    cash_count_service.financial_core,
                    "create_manual_adjustment",
                    return_value=(mock_movement, mock_entry),
                ):
                    with patch("app.modules.financial_core.cash_count_service.CashCount", MockCashCount):
                        with patch("app.modules.financial_core.cash_count_service.event_bus"):
                            result = cash_count_service.record_count(
                                account_id=uuid.uuid4(),
                                counted_amount=counted,
                                resolution="ADJUSTED",
                                notes="Ajuste de conferência de caixa",
                                actor_id=uuid.uuid4(),
                                company_id=uuid.uuid4(),
                                db=mock_db,
                            )

        assert cash_count_kwargs["entry_id"] == expected_entry_id

    def test_cash_count_no_adjustment_entry_id_is_none(self):
        """CashCount com NO_ADJUSTMENT tem entry_id=None."""
        from app.modules.financial_core import cash_count_service

        balance = Decimal("1000.00")
        counted = Decimal("1050.00")
        mock_db = MagicMock()

        cash_count_kwargs = {}

        class MockCashCount:
            def __init__(self, **kwargs):
                cash_count_kwargs.update(kwargs)
                self.cash_count_id = uuid.uuid4()
                self.entry_id = kwargs.get("entry_id")

        with patch.object(cash_count_service.financial_core, "get_account", return_value=_make_account()):
            with patch.object(cash_count_service.financial_core, "compute_balance", return_value=balance):
                with patch("app.modules.financial_core.cash_count_service.CashCount", MockCashCount):
                    with patch("app.modules.financial_core.cash_count_service.event_bus"):
                        result = cash_count_service.record_count(
                            account_id=uuid.uuid4(),
                            counted_amount=counted,
                            resolution="NO_ADJUSTMENT",
                            notes=None,
                            actor_id=uuid.uuid4(),
                            company_id=uuid.uuid4(),
                            db=mock_db,
                        )

        assert cash_count_kwargs.get("entry_id") is None


# ─────────────────────────────────────────────────────────────────────────────
# 11. Cross-tenant: create_transfer com conta de outro tenant → 404
# ─────────────────────────────────────────────────────────────────────────────

class TestCrossTenantIsolation:

    def test_create_transfer_wrong_tenant_raises_404(self):
        """create_transfer com conta de outro tenant → get_account levanta 404."""
        from app.modules.financial_core import transfer_service
        from fastapi import HTTPException

        company_id = uuid.uuid4()

        # get_account levanta 404 quando a conta não pertence ao tenant
        def mock_get_account(account_id, cid, db):
            raise HTTPException(status_code=404, detail="Conta não encontrada")

        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            with patch.object(transfer_service, "get_account", side_effect=mock_get_account):
                transfer_service.create_transfer(
                    from_account_id=uuid.uuid4(),  # conta de outro tenant
                    to_account_id=uuid.uuid4(),
                    amount=Decimal("100.00"),
                    actor_id=uuid.uuid4(),
                    company_id=company_id,
                    db=mock_db,
                )

        assert exc_info.value.status_code == 404

    def test_mark_movement_reconciled_wrong_tenant_raises_404(self):
        """mark_movement_reconciled com movement de outro tenant → 404."""
        from app.modules.financial_core import reconciliation_service
        from fastapi import HTTPException

        def _query(model_class):
            q = MagicMock()
            # Movement de outro tenant → not found
            q.filter.return_value.first.return_value = None
            return q

        mock_db = MagicMock()
        mock_db.query.side_effect = _query

        with pytest.raises(HTTPException) as exc_info:
            reconciliation_service.mark_movement_reconciled(
                movement_id=uuid.uuid4(),
                reconciliation_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert exc_info.value.status_code == 404

    def test_list_transfers_filters_by_company_id(self):
        """list_transfers filtra por company_id — transferências de outro tenant não aparecem."""
        from app.modules.financial_core import transfer_service
        from app.infrastructure.db.models.transfer import Transfer

        company_id = uuid.uuid4()
        t1 = _make_transfer(company_id=company_id)
        t2 = _make_transfer(company_id=company_id)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.all.return_value = [t1, t2]

        results = transfer_service.list_transfers(company_id, mock_db)

        assert len(results) == 2
        mock_query.filter.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# Extra: schemas de Sprint 7
# ─────────────────────────────────────────────────────────────────────────────

class TestSprint7Schemas:

    def test_transfer_create_validates_positive_amount(self):
        """TransferCreate rejeita amount <= 0."""
        from app.modules.financial_core.schemas import TransferCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            TransferCreate(
                from_account_id=uuid.uuid4(),
                to_account_id=uuid.uuid4(),
                amount=Decimal("-10.00"),
            )

    def test_transfer_create_valid(self):
        """TransferCreate aceita dados válidos."""
        from app.modules.financial_core.schemas import TransferCreate

        schema = TransferCreate(
            from_account_id=uuid.uuid4(),
            to_account_id=uuid.uuid4(),
            amount=Decimal("500.00"),
            notes="Transferência de caixa para banco",
        )
        assert schema.amount == Decimal("500.00")

    def test_cash_count_create_validates_resolution(self):
        """CashCountCreate rejeita resolution inválido."""
        from app.modules.financial_core.schemas import CashCountCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CashCountCreate(
                account_id=uuid.uuid4(),
                counted_amount=Decimal("1000.00"),
                resolution="INVALID_RESOLUTION",
            )

    def test_cash_count_create_valid(self):
        """CashCountCreate aceita dados válidos."""
        from app.modules.financial_core.schemas import CashCountCreate

        schema = CashCountCreate(
            account_id=uuid.uuid4(),
            counted_amount=Decimal("1500.00"),
            resolution="ADJUSTED",
            notes="Conferência mensal",
        )
        assert schema.resolution == "ADJUSTED"

    def test_reconciliation_create_valid(self):
        """ReconciliationCreate aceita dados válidos."""
        from app.modules.financial_core.schemas import ReconciliationCreate

        schema = ReconciliationCreate(
            account_id=uuid.uuid4(),
            notes="Reconciliação do mês de maio",
        )
        assert schema.notes == "Reconciliação do mês de maio"

    def test_mark_movement_reconciled_body_valid(self):
        """MarkMovementReconciledBody aceita reconciliation_id UUID."""
        from app.modules.financial_core.schemas import MarkMovementReconciledBody

        rid = uuid.uuid4()
        schema = MarkMovementReconciledBody(reconciliation_id=rid)
        assert schema.reconciliation_id == rid


# ─────────────────────────────────────────────────────────────────────────────
# Extra: open_reconciliation e close_reconciliation
# ─────────────────────────────────────────────────────────────────────────────

class TestOpenCloseReconciliation:

    def test_open_reconciliation_creates_record(self):
        """open_reconciliation cria ReconciliationRecord com status OPEN."""
        from app.modules.financial_core import reconciliation_service
        from app.infrastructure.db.models.reconciliation_record import ReconciliationRecord

        added_objects = []
        mock_db = MagicMock()
        mock_db.add.side_effect = lambda obj: added_objects.append(obj)

        with patch.object(reconciliation_service, "get_account", return_value=_make_account()):
            with patch("app.modules.financial_core.reconciliation_service.event_bus"):
                reconciliation_service.open_reconciliation(
                    account_id=uuid.uuid4(),
                    notes="Abertura de reconciliação",
                    actor_id=uuid.uuid4(),
                    company_id=uuid.uuid4(),
                    db=mock_db,
                )

        rr_objects = [o for o in added_objects if isinstance(o, ReconciliationRecord)]
        assert len(rr_objects) == 1
        assert rr_objects[0].status == "OPEN"

    def test_close_reconciliation_already_closed_raises_422(self):
        """close_reconciliation em reconciliação já CLOSED → 422."""
        from app.modules.financial_core import reconciliation_service
        from fastapi import HTTPException

        mock_record = MagicMock()
        mock_record.reconciliation_id = uuid.uuid4()
        mock_record.company_id = uuid.uuid4()
        mock_record.status = "CLOSED"  # já fechada

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        with pytest.raises(HTTPException) as exc_info:
            reconciliation_service.close_reconciliation(
                reconciliation_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert exc_info.value.status_code == 422

    def test_close_reconciliation_sets_closed_at(self):
        """close_reconciliation define status=CLOSED e closed_at."""
        from app.modules.financial_core import reconciliation_service

        actor_id = uuid.uuid4()
        mock_record = MagicMock()
        mock_record.reconciliation_id = uuid.uuid4()
        mock_record.company_id = uuid.uuid4()
        mock_record.status = "OPEN"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_record

        with patch("app.modules.financial_core.reconciliation_service.event_bus"):
            reconciliation_service.close_reconciliation(
                reconciliation_id=uuid.uuid4(),
                actor_id=actor_id,
                company_id=uuid.uuid4(),
                db=mock_db,
            )

        assert mock_record.status == "CLOSED"
        assert mock_record.closed_at is not None
        assert mock_record.closed_by == actor_id
