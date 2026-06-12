"""
Testes Sprint E — ExternalStatementEntry (conciliação com extrato externo).

Usa mocks (unittest.mock) — sem banco PostgreSQL real (padrão do projeto).

Casos obrigatórios:
  1.  Re-import do mesmo CSV não duplica entradas (line_hash idempotente)
  2.  import_csv retorna contagem correta de imported/skipped_duplicates/auto_matched
  3.  suggest_match encontra o candidato correto (mesmo account, valor, data próxima)
  4.  suggest_match NÃO retorna movement já casado com outra entry
  5.  confirm_match: entry vai para MATCHED, Movement não é alterado
  6.  confirm_match de movement já casado → 409
  7.  confirm_match de entry MATCHED → 422
  8.  dismiss sem reason → 422
  9.  dismiss de entry MATCHED → 422
  10. CSV com valores negativos → direction=OUTFLOW inferido
  11. Cross-tenant: entries de empresa A invisíveis para B (404)
  12. OPERATOR sem config → 403 em import/match/dismiss (require_action)
"""
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.deps import require_action
from app.infrastructure.db.models.external_statement_entry import ExternalStatementEntry
from app.infrastructure.db.models.movement import Movement
from app.modules.financial_core import statement_service
from app.modules.financial_core.statement_service import (
    _line_hash,
    confirm_match,
    dismiss_entry,
    import_csv,
    suggest_match,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_entry(
    company_id=None,
    account_id=None,
    status="PENDING",
    amount=Decimal("150.00"),
    direction="INFLOW",
    occurred=None,
    matched_movement_id=None,
):
    e = MagicMock(spec=ExternalStatementEntry)
    e.id = uuid.uuid4()
    e.company_id = company_id or uuid.uuid4()
    e.account_id = account_id or uuid.uuid4()
    e.occurred_at = occurred or date(2026, 6, 10)
    e.amount = amount
    e.direction = direction
    e.status = status
    e.matched_movement_id = matched_movement_id
    e.dismissed_reason = None
    e.dismissed_at = None
    e.dismissed_by = None
    return e


def _make_movement(
    company_id=None,
    account_id=None,
    type="INFLOW",
    amount=Decimal("150.00"),
    occurred=None,
):
    """SimpleNamespace (não MagicMock): permite detectar mutação acidental."""
    return SimpleNamespace(
        movement_id=uuid.uuid4(),
        company_id=company_id or uuid.uuid4(),
        account_id=account_id or uuid.uuid4(),
        type=type,
        amount=amount,
        occurred_at=occurred or datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc),
        source_type="payment",
        source_id=uuid.uuid4(),
        transfer_id=None,
    )


def _make_db(
    entry_first=None,        # fila de resultados p/ query(ExternalStatementEntry).first()
    entries_all=None,
    movements_all=None,
    movement_first=None,
    existing_hashes=None,    # query(ExternalStatementEntry.line_hash).all()
    matched_ids=None,        # query(ExternalStatementEntry.matched_movement_id).all()
):
    db = MagicMock()
    first_queue = list(entry_first or [])

    def _query(arg):
        q = MagicMock()
        f = q.filter.return_value
        if arg is ExternalStatementEntry:
            f.first.side_effect = lambda: first_queue.pop(0) if first_queue else None
            f.all.return_value = entries_all or []
            f.order_by.return_value.all.return_value = entries_all or []
        elif arg is Movement:
            f.all.return_value = movements_all or []
            f.first.return_value = movement_first
        elif arg is ExternalStatementEntry.line_hash:
            f.all.return_value = [(h,) for h in (existing_hashes or [])]
        elif arg is ExternalStatementEntry.matched_movement_id:
            f.all.return_value = [(m,) for m in (matched_ids or [])]
        else:
            f.first.return_value = None
            f.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


def _added_statement_entries(db):
    return [
        obj for call in db.add.call_args_list
        for obj in call.args
        if isinstance(obj, ExternalStatementEntry)
    ]


# CSV usa vírgula como separador de campo e vírgula decimal entre aspas
_CSV = "\n".join([
    '10/06/2026,"150,00",PIX RECEBIDO',
    '11/06/2026,"-80,00",TARIFA BANCARIA',
    '11/06/2026,"200,00",TED CLIENTE',
])

_MAPPING = {"date": 0, "amount": 1, "description": 2}


# ─── 1. Re-import idempotente ─────────────────────────────────────────────────

class TestImportIdempotent:
    def test_reimport_same_csv_skips_all_lines(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        all_hashes = [_line_hash(ln) for ln in _CSV.splitlines()]

        db = _make_db(existing_hashes=all_hashes)
        result = import_csv(
            db=db, company_id=company_id, account_id=account_id,
            file_content=_CSV.encode(), column_mapping=_MAPPING,
            created_by=uuid.uuid4(),
        )

        assert result["imported"] == 0
        assert result["skipped_duplicates"] == 3
        assert _added_statement_entries(db) == []

    def test_duplicate_line_within_same_file_counted_once(self):
        csv_dup = _CSV + "\n" + _CSV.splitlines()[0]
        db = _make_db()
        result = import_csv(
            db=db, company_id=uuid.uuid4(), account_id=uuid.uuid4(),
            file_content=csv_dup.encode(), column_mapping=_MAPPING,
            created_by=uuid.uuid4(),
        )
        assert result["imported"] == 3
        assert result["skipped_duplicates"] == 1


# ─── 2. Contagens do import ───────────────────────────────────────────────────

class TestImportCounts:
    def test_counts_imported_skipped_auto_matched(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        lines = _CSV.splitlines()

        # linha 2 já importada anteriormente
        existing = [_line_hash(lines[1])]
        # candidato compatível apenas com a linha 1 (150.00 INFLOW em 10/06)
        candidate = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
            occurred=datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
        )

        db = _make_db(existing_hashes=existing, movements_all=[candidate])
        result = import_csv(
            db=db, company_id=company_id, account_id=account_id,
            file_content=_CSV.encode(), column_mapping=_MAPPING,
            created_by=uuid.uuid4(),
        )

        assert result["imported"] == 2
        assert result["skipped_duplicates"] == 1
        assert result["auto_matched"] == 1
        assert result["batch_id"] is not None

        # auto-match é apenas sugestão: nada persiste como MATCHED
        added = _added_statement_entries(db)
        assert len(added) == 2
        assert all(e.status == "PENDING" for e in added)
        assert all(e.matched_movement_id is None for e in added)
        # todas as entries do mesmo upload compartilham o batch_id
        assert {e.import_batch_id for e in added} == {result["batch_id"]}

    def test_header_line_skipped_as_invalid(self):
        csv_with_header = "data,valor,descricao\n" + _CSV
        db = _make_db()
        result = import_csv(
            db=db, company_id=uuid.uuid4(), account_id=uuid.uuid4(),
            file_content=csv_with_header.encode(), column_mapping=_MAPPING,
            created_by=uuid.uuid4(),
        )
        assert result["imported"] == 3
        assert result["skipped_invalid"] == 1

    def test_mapping_without_date_or_amount_raises_422(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            import_csv(
                db=db, company_id=uuid.uuid4(), account_id=uuid.uuid4(),
                file_content=_CSV.encode(), column_mapping={"date": 0},
                created_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 422


# ─── 3. suggest_match encontra o candidato correto ────────────────────────────

class TestSuggestMatch:
    def test_finds_correct_candidate(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        entry = _make_entry(
            company_id=company_id, account_id=account_id,
            amount=Decimal("150.00"), direction="INFLOW",
            occurred=date(2026, 6, 10),
        )

        good = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
            occurred=datetime(2026, 6, 11, 9, 0, tzinfo=timezone.utc),
        )
        wrong_amount = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("999.00"),
        )
        wrong_date = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
            occurred=datetime(2026, 6, 20, 9, 0, tzinfo=timezone.utc),
        )
        wrong_account = _make_movement(
            company_id=company_id, account_id=uuid.uuid4(),
            type="INFLOW", amount=Decimal("150.00"),
        )
        wrong_direction = _make_movement(
            company_id=company_id, account_id=account_id,
            type="OUTFLOW", amount=Decimal("150.00"),
        )

        db = _make_db(
            entry_first=[entry],
            movements_all=[wrong_amount, good, wrong_date, wrong_account, wrong_direction],
        )
        result = suggest_match(db, company_id, entry.id)
        assert result == [good]

    def test_amount_tolerance_one_cent(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        entry = _make_entry(
            company_id=company_id, account_id=account_id,
            amount=Decimal("150.00"), direction="INFLOW",
        )
        near = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.01"),
        )
        db = _make_db(entry_first=[entry], movements_all=[near])
        assert suggest_match(db, company_id, entry.id) == [near]

    def test_ordered_by_date_proximity(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        entry = _make_entry(
            company_id=company_id, account_id=account_id,
            amount=Decimal("150.00"), direction="INFLOW",
            occurred=date(2026, 6, 10),
        )
        far = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
            occurred=datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc),
        )
        close = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
            occurred=datetime(2026, 6, 10, 14, 0, tzinfo=timezone.utc),
        )
        db = _make_db(entry_first=[entry], movements_all=[far, close])
        assert suggest_match(db, company_id, entry.id) == [close, far]

    def test_non_pending_entry_raises_422(self):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status="MATCHED")
        db = _make_db(entry_first=[entry])
        with pytest.raises(HTTPException) as exc:
            suggest_match(db, company_id, entry.id)
        assert exc.value.status_code == 422


# ─── 4. suggest_match exclui movement já casado ───────────────────────────────

class TestSuggestMatchExcludesTaken:
    def test_excludes_movement_matched_to_other_entry(self):
        company_id = uuid.uuid4()
        account_id = uuid.uuid4()
        entry = _make_entry(
            company_id=company_id, account_id=account_id,
            amount=Decimal("150.00"), direction="INFLOW",
        )
        taken = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
        )
        free = _make_movement(
            company_id=company_id, account_id=account_id,
            type="INFLOW", amount=Decimal("150.00"),
        )
        db = _make_db(
            entry_first=[entry],
            movements_all=[taken, free],
            matched_ids=[taken.movement_id],
        )
        assert suggest_match(db, company_id, entry.id) == [free]


# ─── 5. confirm_match: MATCHED + Movement intocado ────────────────────────────

class TestConfirmMatch:
    def test_entry_matched_and_movement_untouched(self):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status="PENDING")
        movement = _make_movement(company_id=company_id, account_id=entry.account_id)
        snapshot_before = dict(vars(movement))

        # 1ª query: entry; 2ª query: já-casado? → None
        db = _make_db(entry_first=[entry, None], movement_first=movement)
        result = confirm_match(
            db=db, company_id=company_id, entry_id=entry.id,
            movement_id=movement.movement_id, confirmed_by=uuid.uuid4(),
        )

        assert result.status == "MATCHED"
        assert result.matched_movement_id == movement.movement_id
        assert db.commit.called
        # Movement 100% intocado — vínculo unidirecional na entry
        assert vars(movement) == snapshot_before

    def test_movement_of_other_tenant_raises_404(self):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status="PENDING")
        db = _make_db(entry_first=[entry, None], movement_first=None)
        with pytest.raises(HTTPException) as exc:
            confirm_match(
                db=db, company_id=company_id, entry_id=entry.id,
                movement_id=uuid.uuid4(), confirmed_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 404


# ─── 6. confirm_match de movement já casado → 409 ─────────────────────────────

class TestConfirmMatchConflict:
    def test_movement_already_matched_raises_409(self):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status="PENDING")
        movement = _make_movement(company_id=company_id)
        other_entry = _make_entry(
            company_id=company_id, status="MATCHED",
            matched_movement_id=movement.movement_id,
        )
        db = _make_db(entry_first=[entry, other_entry], movement_first=movement)
        with pytest.raises(HTTPException) as exc:
            confirm_match(
                db=db, company_id=company_id, entry_id=entry.id,
                movement_id=movement.movement_id, confirmed_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 409
        assert entry.status == "PENDING"  # nada persistido


# ─── 7. confirm_match de entry MATCHED → 422 ──────────────────────────────────

class TestConfirmMatchInvalidStatus:
    @pytest.mark.parametrize("status", ["MATCHED", "DISMISSED"])
    def test_non_pending_entry_raises_422(self, status):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status=status)
        db = _make_db(entry_first=[entry])
        with pytest.raises(HTTPException) as exc:
            confirm_match(
                db=db, company_id=company_id, entry_id=entry.id,
                movement_id=uuid.uuid4(), confirmed_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 422


# ─── 8 e 9. dismiss ───────────────────────────────────────────────────────────

class TestDismiss:
    @pytest.mark.parametrize("reason", [None, "", "   "])
    def test_dismiss_without_reason_raises_422(self, reason):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            dismiss_entry(
                db=db, company_id=uuid.uuid4(), entry_id=uuid.uuid4(),
                reason=reason, dismissed_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 422
        assert not db.commit.called

    @pytest.mark.parametrize("status", ["MATCHED", "DISMISSED"])
    def test_dismiss_non_pending_raises_422(self, status):
        company_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status=status)
        db = _make_db(entry_first=[entry])
        with pytest.raises(HTTPException) as exc:
            dismiss_entry(
                db=db, company_id=company_id, entry_id=entry.id,
                reason="lançamento duplicado", dismissed_by=uuid.uuid4(),
            )
        assert exc.value.status_code == 422

    def test_dismiss_pending_persists_reason_and_audit_fields(self):
        company_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        entry = _make_entry(company_id=company_id, status="PENDING")
        db = _make_db(entry_first=[entry])

        result = dismiss_entry(
            db=db, company_id=company_id, entry_id=entry.id,
            reason="tarifa bancária — sem movement correspondente",
            dismissed_by=actor_id,
        )

        assert result.status == "DISMISSED"
        assert result.dismissed_reason == "tarifa bancária — sem movement correspondente"
        assert result.dismissed_at is not None
        assert result.dismissed_by == actor_id
        assert db.commit.called


# ─── 10. Valores negativos → OUTFLOW inferido ─────────────────────────────────

class TestDirectionInference:
    def test_negative_amount_infers_outflow(self):
        db = _make_db()
        import_csv(
            db=db, company_id=uuid.uuid4(), account_id=uuid.uuid4(),
            file_content=_CSV.encode(), column_mapping=_MAPPING,
            created_by=uuid.uuid4(),
        )
        added = _added_statement_entries(db)
        by_desc = {e.description: e for e in added}

        assert by_desc["TARIFA BANCARIA"].direction == "OUTFLOW"
        assert by_desc["TARIFA BANCARIA"].amount == Decimal("80.00")  # abs()
        assert by_desc["PIX RECEBIDO"].direction == "INFLOW"
        assert by_desc["TED CLIENTE"].direction == "INFLOW"

    def test_explicit_direction_column_wins_over_sign(self):
        csv_dir = '10/06/2026,"150,00",ESTORNO,D'
        db = _make_db()
        import_csv(
            db=db, company_id=uuid.uuid4(), account_id=uuid.uuid4(),
            file_content=csv_dir.encode(),
            column_mapping={"date": 0, "amount": 1, "description": 2, "direction": 3},
            created_by=uuid.uuid4(),
        )
        added = _added_statement_entries(db)
        assert added[0].direction == "OUTFLOW"


# ─── 11. Cross-tenant ─────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_entry_of_other_company_returns_404(self):
        # Query filtrada por company_id retorna None → 404 (entry da empresa A
        # invisível para a empresa B)
        db = _make_db(entry_first=[None])
        for fn, kwargs in [
            (suggest_match, {}),
            (confirm_match, {"movement_id": uuid.uuid4(), "confirmed_by": uuid.uuid4()}),
            (dismiss_entry, {"reason": "x", "dismissed_by": uuid.uuid4()}),
        ]:
            db = _make_db(entry_first=[None])
            with pytest.raises(HTTPException) as exc:
                fn(db, uuid.uuid4(), uuid.uuid4(), **kwargs)
            assert exc.value.status_code == 404


# ─── 12. OPERATOR sem config → 403 ────────────────────────────────────────────

def _make_user(role="OPERATOR"):
    u = MagicMock()
    u.role = role
    u.company_id = uuid.uuid4()
    return u


def _make_deps_db(overrides=None):
    """db para require_action: query(TenantConfig).first() → config mock."""
    db = MagicMock()
    config = MagicMock()
    config.permission_overrides = overrides or {}
    db.query.return_value.filter.return_value.first.return_value = config
    return db


class TestOperatorRBAC:
    @pytest.mark.parametrize(
        "action", ["statement_import", "statement_match", "statement_dismiss"]
    )
    def test_operator_without_override_gets_403(self, action):
        dep = require_action(action)
        with pytest.raises(HTTPException) as exc:
            dep(user=_make_user("OPERATOR"), db=_make_deps_db())
        assert exc.value.status_code == 403

    def test_operator_with_override_passes(self):
        dep = require_action("statement_import")
        db = _make_deps_db({"OPERATOR": {"statement_import": True}})
        user = _make_user("OPERATOR")
        assert dep(user=user, db=db) is user

    @pytest.mark.parametrize("role", ["OWNER", "ADMIN"])
    def test_owner_admin_pass_by_default(self, role):
        dep = require_action("statement_dismiss")
        user = _make_user(role)
        assert dep(user=user, db=_make_deps_db()) is user
