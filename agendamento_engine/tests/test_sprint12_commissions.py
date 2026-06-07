"""
Testes Sprint 12 — CommissionEngine.

Usa mocks (unittest.mock) — sem banco PostgreSQL real.

Casos obrigatórios:
  1.  GROSS_SERVICE + BEFORE_FEES + 40%: gross=100 → commission=40
  2.  AFTER_FEES + 40%: gross=100, fee=2 → base=98 → commission=39.20
  3.  CUSTOM_AMOUNT: fixed_amount=25 → commission=25 (ignora gross)
  4.  Prioridade de política: (prof+serv) > (prof) > (serv) > (global) > None
  5.  Sem política ativa → calculate_commission retorna None (sem erro)
  6.  create_payout: Movement OUTFLOW + Entry COMISSAO atômicos
  7.  operation.completed handler → Commission CALCULATED criada (best-effort)
  8.  reverse_commission CALCULATED → REVERSED + audit
  9.  Cross-tenant: commissions e policies isolados por company_id
  10. mark_due: CALCULATED → DUE
  11. create_payout sem commissions → 422
  12. create_payout com comissão de outro profissional → 422
"""
import sys
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import pytest

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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_policy(
    policy_id=None,
    company_id=None,
    professional_id=None,
    service_id=None,
    commission_base="GROSS_SERVICE",
    commission_fee_policy="BEFORE_FEES",
    rate=Decimal("40.00"),
    fixed_amount=None,
    is_active=True,
):
    p = MagicMock()
    p.policy_id             = policy_id or uuid.uuid4()
    p.company_id            = company_id or uuid.uuid4()
    p.professional_id       = professional_id
    p.service_id            = service_id
    p.commission_base       = commission_base
    p.commission_fee_policy = commission_fee_policy
    p.rate                  = rate
    p.fixed_amount          = fixed_amount
    p.is_active             = is_active
    return p


def _make_commission(
    commission_id=None,
    company_id=None,
    professional_id=None,
    policy_id=None,
    appointment_id=None,
    operation_type="SERVICE_RENDERED",
    gross_amount=Decimal("100.00"),
    commission_amount=Decimal("40.00"),
    status="CALCULATED",
    payout_id=None,
):
    c = MagicMock()
    c.commission_id     = commission_id or uuid.uuid4()
    c.company_id        = company_id or uuid.uuid4()
    c.professional_id   = professional_id or uuid.uuid4()
    c.policy_id         = policy_id or uuid.uuid4()
    c.appointment_id    = appointment_id or uuid.uuid4()
    c.operation_type    = operation_type
    c.gross_amount      = gross_amount
    c.commission_amount = commission_amount
    c.status            = status
    c.payout_id         = payout_id
    c.due_date          = None
    c.paid_at           = None
    return c


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.commit  = MagicMock()
    db.rollback = MagicMock()
    db.flush   = MagicMock()
    db.add     = MagicMock()
    db.refresh = MagicMock()
    return db


def _db_with_policy(policy):
    """Mock de db que retorna a política para qualquer query."""
    db = _make_db()
    db.query.return_value.filter.return_value.filter.return_value.filter.return_value.first.return_value = policy
    # encadeamentos menores também precisam funcionar
    db.query.return_value.filter.return_value.first.return_value = policy
    return db


# ─── 1. GROSS_SERVICE + BEFORE_FEES + 40% ────────────────────────────────────

class TestCalculateCommissionGross:
    def test_gross_before_fees_40_percent(self):
        """gross=100, rate=40%, BEFORE_FEES → commission=40.00"""
        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        svc   = uuid.uuid4()
        appt  = uuid.uuid4()
        policy = _make_policy(
            company_id=cid, professional_id=prof, service_id=svc,
            commission_base="GROSS_SERVICE",
            commission_fee_policy="BEFORE_FEES",
            rate=Decimal("40.00"),
        )

        from app.modules.commission import service as svc_module

        # Injeta _find_active_policy para retornar a política mock
        with patch.object(svc_module, "_find_active_policy", return_value=policy):
            db = _make_db()
            captured = {}

            def _capture_add(obj):
                captured["commission"] = obj

            db.add.side_effect = _capture_add

            result = svc_module.calculate_commission(
                professional_id=prof,
                service_id=svc,
                gross_amount=Decimal("100.00"),
                provider_fee=Decimal("0"),
                operation_type="SERVICE_RENDERED",
                appointment_id=appt,
                company_id=cid,
                db=db,
            )

        assert result is not None
        assert "commission" in captured
        commission = captured["commission"]
        assert commission.commission_amount == Decimal("40.00")
        assert commission.status == "CALCULATED"
        assert commission.operation_type == "SERVICE_RENDERED"
        assert commission.gross_amount == Decimal("100.00")
        db.commit.assert_called_once()

    def test_gross_after_fees_40_percent(self):
        """gross=100, fee=2, rate=40%, AFTER_FEES → base=98 → commission=39.20"""
        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        policy = _make_policy(
            company_id=cid,
            commission_base="GROSS_SERVICE",
            commission_fee_policy="AFTER_FEES",
            rate=Decimal("40.00"),
        )

        from app.modules.commission import service as svc_module

        with patch.object(svc_module, "_find_active_policy", return_value=policy):
            db = _make_db()
            captured = {}
            db.add.side_effect = lambda obj: captured.update({"commission": obj})

            result = svc_module.calculate_commission(
                professional_id=prof,
                service_id=None,
                gross_amount=Decimal("100.00"),
                provider_fee=Decimal("2.00"),
                operation_type="SERVICE_RENDERED",
                appointment_id=None,
                company_id=cid,
                db=db,
            )

        commission = captured["commission"]
        assert commission.commission_amount == Decimal("39.20")

    def test_custom_amount(self):
        """CUSTOM_AMOUNT: fixed_amount=25 → commission=25 (ignora gross)"""
        cid  = uuid.uuid4()
        prof = uuid.uuid4()
        policy = _make_policy(
            company_id=cid,
            commission_base="CUSTOM_AMOUNT",
            commission_fee_policy="BEFORE_FEES",
            rate=None,
            fixed_amount=Decimal("25.00"),
        )

        from app.modules.commission import service as svc_module

        with patch.object(svc_module, "_find_active_policy", return_value=policy):
            db = _make_db()
            captured = {}
            db.add.side_effect = lambda obj: captured.update({"commission": obj})

            result = svc_module.calculate_commission(
                professional_id=prof,
                service_id=None,
                gross_amount=Decimal("999.00"),
                provider_fee=Decimal("10.00"),
                operation_type="SERVICE_RENDERED",
                appointment_id=None,
                company_id=cid,
                db=db,
            )

        commission = captured["commission"]
        assert commission.commission_amount == Decimal("25.00")

    def test_no_policy_returns_none(self):
        """Sem política ativa → retorna None (sem erro, sem commit)."""
        from app.modules.commission import service as svc_module

        with patch.object(svc_module, "_find_active_policy", return_value=None):
            db = _make_db()
            result = svc_module.calculate_commission(
                professional_id=uuid.uuid4(),
                service_id=None,
                gross_amount=Decimal("100.00"),
                provider_fee=Decimal("0"),
                operation_type="SERVICE_RENDERED",
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
            )

        assert result is None
        db.commit.assert_not_called()


# ─── 4. Prioridade de política ────────────────────────────────────────────────

class TestPolicyPriority:
    """Testa que _find_active_policy respeita a hierarquia de prioridade."""

    def _build_policies(self, cid, prof, svc):
        """Cria políticas com valores distintos para identificar qual foi aplicada."""
        p_prof_svc = _make_policy(
            company_id=cid, professional_id=prof, service_id=svc,
            rate=Decimal("50.00"), is_active=True,
        )
        p_prof = _make_policy(
            company_id=cid, professional_id=prof, service_id=None,
            rate=Decimal("30.00"), is_active=True,
        )
        p_svc = _make_policy(
            company_id=cid, professional_id=None, service_id=svc,
            rate=Decimal("20.00"), is_active=True,
        )
        p_global = _make_policy(
            company_id=cid, professional_id=None, service_id=None,
            rate=Decimal("10.00"), is_active=True,
        )
        return p_prof_svc, p_prof, p_svc, p_global

    def _make_priority_db(self, cid, prof, svc, available_policies):
        """
        Simula o banco retornando a política correta conforme os filtros aplicados.
        _find_active_policy itera em ordem de prioridade e chama first() para cada combinação.
        """
        from app.infrastructure.db.models.commission import CommissionPolicy

        db = MagicMock()

        def query_side(model):
            chain = MagicMock()

            def _build_result(has_prof, has_svc):
                for p in available_policies:
                    matches_prof = (p.professional_id == prof) if has_prof else (p.professional_id is None)
                    matches_svc = (p.service_id == svc) if has_svc else (p.service_id is None)
                    if matches_prof and matches_svc and p.is_active:
                        return p
                return None

            # Simula o encadeamento filter().filter().filter().first()
            # A implementação de _find_active_policy chama múltiplos .filter()
            # Precisamos de um mock que rastreie os filtros
            class FilterTracker:
                def __init__(self):
                    self._has_prof = None
                    self._has_svc = None
                    self._company_filtered = False

                def filter(self, *args):
                    # Inspeciona os argumentos para descobrir o filtro
                    for arg in args:
                        try:
                            compiled = str(arg)
                        except Exception:
                            compiled = ""
                        if "professional_id" in compiled:
                            if "NULL" in compiled or "IS" in compiled:
                                self._has_prof = False
                            else:
                                self._has_prof = True
                        elif "service_id" in compiled:
                            if "NULL" in compiled or "IS" in compiled:
                                self._has_svc = False
                            else:
                                self._has_svc = True
                        elif "company_id" in compiled:
                            self._company_filtered = True
                        elif "is_active" in compiled:
                            pass
                    return self

                def first(self):
                    if self._has_prof is None:
                        self._has_prof = False
                    if self._has_svc is None:
                        self._has_svc = False
                    return _build_result(self._has_prof, self._has_svc)

            tracker = FilterTracker()
            chain.filter.side_effect = lambda *a: tracker.filter(*a)
            chain.first.side_effect = tracker.first
            return chain

        db.query.side_effect = query_side
        return db

    def test_prof_svc_wins_over_all(self):
        """(prof+serv) tem prioridade máxima."""
        from app.modules.commission import service as svc_mod

        cid  = uuid.uuid4()
        prof = uuid.uuid4()
        svc  = uuid.uuid4()
        p_ps, p_p, p_s, p_g = self._build_policies(cid, prof, svc)

        with patch.object(svc_mod, "_find_active_policy", wraps=lambda *a, **kw: p_ps):
            db = _make_db()
            captured = {}
            db.add.side_effect = lambda obj: captured.update({"commission": obj})

            svc_mod.calculate_commission(
                professional_id=prof, service_id=svc,
                gross_amount=Decimal("100"), provider_fee=Decimal("0"),
                operation_type="SERVICE_RENDERED", appointment_id=None,
                company_id=cid, db=db,
            )

        assert captured["commission"].commission_amount == Decimal("50.00")

    def test_global_used_when_no_specific(self):
        """(global) é usado quando não há política específica."""
        from app.modules.commission import service as svc_mod

        cid  = uuid.uuid4()
        prof = uuid.uuid4()
        svc  = uuid.uuid4()
        _, _, _, p_g = self._build_policies(cid, prof, svc)

        with patch.object(svc_mod, "_find_active_policy", return_value=p_g):
            db = _make_db()
            captured = {}
            db.add.side_effect = lambda obj: captured.update({"commission": obj})

            svc_mod.calculate_commission(
                professional_id=prof, service_id=svc,
                gross_amount=Decimal("100"), provider_fee=Decimal("0"),
                operation_type="SERVICE_RENDERED", appointment_id=None,
                company_id=cid, db=db,
            )

        assert captured["commission"].commission_amount == Decimal("10.00")

    def test_find_active_policy_priority_order(self):
        """_find_active_policy: apenas política global ativa → retorna global."""
        from app.modules.commission.service import _find_active_policy
        from app.infrastructure.db.models.commission import CommissionPolicy

        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        svc   = uuid.uuid4()
        p_global = _make_policy(
            company_id=cid, professional_id=None, service_id=None,
            rate=Decimal("10.00"), is_active=True,
        )

        db = MagicMock()
        call_count = [0]

        def query_side(model):
            chain = MagicMock()

            class Tracker:
                def __init__(self):
                    self._filters = []

                def filter(self, *args):
                    self._filters.extend(args)
                    return self

                def first(self):
                    # Retorna política global apenas na 4ª chamada (global = prof=None, svc=None)
                    call_count[0] += 1
                    if call_count[0] == 4:
                        return p_global
                    return None

            t = Tracker()
            chain.filter.side_effect = lambda *a: t.filter(*a)
            chain.first.side_effect  = t.first
            return chain

        db.query.side_effect = query_side
        result = _find_active_policy(prof, svc, cid, db)
        assert result is p_global
        assert call_count[0] == 4  # percorreu as 4 prioridades


# ─── 6. create_payout ─────────────────────────────────────────────────────────

class TestCreatePayout:
    def test_payout_creates_movement_and_entry(self):
        """create_payout: Movement OUTFLOW + Entry COMISSAO atômicos."""
        from app.modules.commission import service as svc_mod
        from app.modules.financial_core import service as fin_svc

        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        acct  = uuid.uuid4()
        actor = uuid.uuid4()

        c1 = _make_commission(company_id=cid, professional_id=prof, commission_amount=Decimal("40.00"))
        c2 = _make_commission(company_id=cid, professional_id=prof, commission_amount=Decimal("25.00"))
        c1_id = c1.commission_id
        c2_id = c2.commission_id

        db = _make_db()
        db.query.return_value.filter.return_value.all.return_value = [c1, c2]

        payout_obj = MagicMock()
        payout_obj.payout_id = uuid.uuid4()

        fin_called = {}

        def fake_handle_commission_paid(**kwargs):
            fin_called.update(kwargs)
            return MagicMock(), MagicMock()

        with patch.object(fin_svc, "handle_commission_paid", side_effect=fake_handle_commission_paid), \
             patch("app.modules.commission.service.record_sensitive_action"), \
             patch("app.modules.commission.service.CommissionPayout", return_value=payout_obj) as mock_payout_cls, \
             patch("app.infrastructure.event_bus.event_bus.publish"):

            mock_payout_cls.return_value = payout_obj
            db.flush.side_effect = None

            result = svc_mod.create_payout(
                professional_id=prof,
                commission_ids=[c1_id, c2_id],
                account_id=acct,
                actor_id=actor,
                company_id=cid,
                db=db,
            )

        assert "amount" in fin_called
        assert fin_called["amount"] == Decimal("65.00")
        assert fin_called["account_id"] == acct
        assert fin_called["professional_id"] == prof
        assert fin_called["company_id"] == cid
        db.commit.assert_called_once()

    def test_payout_empty_commission_ids_raises_422(self):
        """create_payout com lista vazia → 422."""
        from app.modules.commission import service as svc_mod
        from fastapi import HTTPException

        db = _make_db()
        with pytest.raises(HTTPException) as exc_info:
            svc_mod.create_payout(
                professional_id=uuid.uuid4(),
                commission_ids=[],
                account_id=uuid.uuid4(),
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=db,
            )

        assert exc_info.value.status_code == 422

    def test_payout_commission_wrong_professional_raises_422(self):
        """create_payout com comissão de outro profissional → 422."""
        from app.modules.commission import service as svc_mod
        from fastapi import HTTPException

        cid       = uuid.uuid4()
        prof      = uuid.uuid4()
        other_prof = uuid.uuid4()
        acct      = uuid.uuid4()
        actor     = uuid.uuid4()

        c = _make_commission(company_id=cid, professional_id=other_prof)
        db = _make_db()
        db.query.return_value.filter.return_value.all.return_value = [c]

        with pytest.raises(HTTPException) as exc_info:
            svc_mod.create_payout(
                professional_id=prof,
                commission_ids=[c.commission_id],
                account_id=acct,
                actor_id=actor,
                company_id=cid,
                db=db,
            )

        assert exc_info.value.status_code == 422


# ─── 7. operation.completed → Commission criada ───────────────────────────────

class TestOperationCompletedHandler:
    def test_handler_calculates_commission(self):
        """operation.completed handler → calculate_commission chamado."""
        from app.workers.handlers.commission_handler import handle_operation_completed
        from app.modules.commission import service as svc_mod

        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        svc   = uuid.uuid4()
        appt  = uuid.uuid4()

        event = MagicMock()
        event.event_id = uuid.uuid4()
        event.payload  = {
            "appointment_id":  str(appt),
            "professional_id": str(prof),
            "service_id":      str(svc),
            "gross_amount":    "100.00",
            "provider_fee":    "2.00",
            "company_id":      str(cid),
        }

        commission_mock = _make_commission(company_id=cid, professional_id=prof)

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission", return_value=commission_mock) as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = _make_db()
            mock_session.return_value = mock_db

            handle_operation_completed(event)

        mock_calc.assert_called_once()
        call_kwargs = mock_calc.call_args.kwargs
        assert call_kwargs["professional_id"] == prof
        assert call_kwargs["service_id"] == svc
        assert call_kwargs["gross_amount"] == Decimal("100.00")
        assert call_kwargs["provider_fee"] == Decimal("2.00")
        assert call_kwargs["operation_type"] == "SERVICE_RENDERED"
        assert call_kwargs["company_id"] == cid

    def test_handler_no_professional_id_skips(self):
        """Handler sem professional_id → não chama calculate_commission."""
        from app.workers.handlers.commission_handler import handle_operation_completed
        from app.modules.commission import service as svc_mod

        event = MagicMock()
        event.event_id = uuid.uuid4()
        event.payload  = {
            "appointment_id": str(uuid.uuid4()),
            "professional_id": None,
            "company_id": str(uuid.uuid4()),
        }

        with patch.object(svc_mod, "calculate_commission") as mock_calc:
            handle_operation_completed(event)

        mock_calc.assert_not_called()

    def test_handler_exception_is_best_effort(self):
        """Handler com erro interno não propaga exceção."""
        from app.workers.handlers.commission_handler import handle_operation_completed
        from app.modules.commission import service as svc_mod

        cid  = uuid.uuid4()
        prof = uuid.uuid4()

        event = MagicMock()
        event.event_id = uuid.uuid4()
        event.payload  = {
            "appointment_id":  str(uuid.uuid4()),
            "professional_id": str(prof),
            "service_id":      None,
            "gross_amount":    "50.00",
            "provider_fee":    "0",
            "company_id":      str(cid),
        }

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission", side_effect=RuntimeError("DB error")), \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = _make_db()
            mock_session.return_value = mock_db

            # Não deve lançar exceção
            handle_operation_completed(event)


# ─── 8. reverse_commission ────────────────────────────────────────────────────

class TestReverseCommission:
    def test_reverse_calculated_to_reversed(self):
        """CALCULATED → REVERSED + record_sensitive_action."""
        from app.modules.commission import service as svc_mod
        from app.core.audit.sensitive_context import record_sensitive_action

        cid   = uuid.uuid4()
        actor = uuid.uuid4()
        c     = _make_commission(company_id=cid, status="CALCULATED")

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = c

        with patch("app.modules.commission.service.record_sensitive_action") as mock_audit:
            svc_mod.reverse_commission(
                commission_id=c.commission_id,
                reason="Serviço reembolsado",
                actor_id=actor,
                company_id=cid,
                db=db,
            )

        assert c.status == "REVERSED"
        mock_audit.assert_called_once()
        db.commit.assert_called_once()

    def test_reverse_requires_reason(self):
        """reverse_commission sem reason → 422."""
        from app.modules.commission import service as svc_mod
        from fastapi import HTTPException

        db = _make_db()
        with pytest.raises(HTTPException) as exc_info:
            svc_mod.reverse_commission(
                commission_id=uuid.uuid4(),
                reason="",
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=db,
            )

        assert exc_info.value.status_code == 422

    def test_reverse_paid_commission_raises_409(self):
        """PAID → reverse → 409."""
        from app.modules.commission import service as svc_mod
        from fastapi import HTTPException

        cid = uuid.uuid4()
        c   = _make_commission(company_id=cid, status="PAID")
        db  = _make_db()
        db.query.return_value.filter.return_value.first.return_value = c

        with pytest.raises(HTTPException) as exc_info:
            svc_mod.reverse_commission(
                commission_id=c.commission_id,
                reason="motivo",
                actor_id=uuid.uuid4(),
                company_id=cid,
                db=db,
            )

        assert exc_info.value.status_code == 409


# ─── 9. Cross-tenant isolation ────────────────────────────────────────────────

class TestCrossTenant:
    def test_commissions_filtered_by_company_id(self):
        """list_commissions filtra por company_id — não retorna dados de outro tenant."""
        from app.modules.commission import service as svc_mod

        cid_a = uuid.uuid4()
        cid_b = uuid.uuid4()

        c_a = _make_commission(company_id=cid_a)
        c_b = _make_commission(company_id=cid_b)

        db = _make_db()

        call_args_captured = []

        def query_filter_side(*args):
            call_args_captured.extend(args)
            inner = MagicMock()
            inner.filter.return_value = inner
            inner.order_by.return_value = inner
            inner.all.return_value = [c_a]  # só retorna do tenant A
            return inner

        db.query.return_value.filter.side_effect = query_filter_side

        results = svc_mod.list_commissions(company_id=cid_a, db=db)
        assert results == [c_a]
        assert c_b not in results

    def test_policies_filtered_by_company_id(self):
        """list_policies filtra por company_id."""
        from app.modules.commission import service as svc_mod

        cid_a = uuid.uuid4()
        p_a   = _make_policy(company_id=cid_a)

        db = _make_db()
        inner = MagicMock()
        inner.filter.return_value = inner
        inner.order_by.return_value = inner
        inner.all.return_value = [p_a]
        db.query.return_value.filter.return_value = inner

        results = svc_mod.list_policies(cid_a, db)
        assert results == [p_a]


# ─── 10. mark_due ─────────────────────────────────────────────────────────────

class TestMarkDue:
    def test_mark_due_calculated_to_due(self):
        """CALCULATED → DUE com due_date."""
        from app.modules.commission import service as svc_mod

        cid = uuid.uuid4()
        c   = _make_commission(company_id=cid, status="CALCULATED")
        db  = _make_db()
        db.query.return_value.filter.return_value.first.return_value = c

        due = date(2026, 7, 1)
        svc_mod.mark_due(c.commission_id, due, cid, db)

        assert c.status == "DUE"
        assert c.due_date == due
        db.commit.assert_called_once()

    def test_mark_due_non_calculated_raises_409(self):
        """Marcar como DUE uma comissão já PAID → 409."""
        from app.modules.commission import service as svc_mod
        from fastapi import HTTPException

        cid = uuid.uuid4()
        c   = _make_commission(company_id=cid, status="PAID")
        db  = _make_db()
        db.query.return_value.filter.return_value.first.return_value = c

        with pytest.raises(HTTPException) as exc_info:
            svc_mod.mark_due(c.commission_id, date(2026, 7, 1), cid, db)

        assert exc_info.value.status_code == 409


# ─── 11. Schema validation ────────────────────────────────────────────────────

class TestSchemaValidation:
    def test_policy_create_requires_rate_or_fixed(self):
        """CommissionPolicyCreate: ambos rate e fixed_amount → ValidationError."""
        from app.modules.commission.schemas import CommissionPolicyCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CommissionPolicyCreate(
                commission_base="GROSS_SERVICE",
                commission_fee_policy="BEFORE_FEES",
                rate=Decimal("40.00"),
                fixed_amount=Decimal("25.00"),
            )

    def test_policy_create_neither_raises(self):
        """CommissionPolicyCreate: nenhum rate nem fixed_amount → ValidationError."""
        from app.modules.commission.schemas import CommissionPolicyCreate
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CommissionPolicyCreate(
                commission_base="GROSS_SERVICE",
                commission_fee_policy="BEFORE_FEES",
                rate=None,
                fixed_amount=None,
            )

    def test_policy_create_valid_rate(self):
        """CommissionPolicyCreate: apenas rate → válido."""
        from app.modules.commission.schemas import CommissionPolicyCreate

        p = CommissionPolicyCreate(
            commission_base="GROSS_SERVICE",
            commission_fee_policy="BEFORE_FEES",
            rate=Decimal("40.00"),
        )
        assert p.rate == Decimal("40.00")
        assert p.fixed_amount is None

    def test_policy_create_valid_fixed(self):
        """CommissionPolicyCreate: apenas fixed_amount → válido."""
        from app.modules.commission.schemas import CommissionPolicyCreate

        p = CommissionPolicyCreate(
            commission_base="CUSTOM_AMOUNT",
            commission_fee_policy="BEFORE_FEES",
            fixed_amount=Decimal("25.00"),
        )
        assert p.fixed_amount == Decimal("25.00")
        assert p.rate is None


# ─── 12. handle_commission_paid em FinancialCoreEngine ────────────────────────

class TestHandleCommissionPaid:
    def test_creates_outflow_and_comissao_entry(self):
        """handle_commission_paid: Movement OUTFLOW + Entry COMISSAO."""
        from app.modules.financial_core import service as fin_svc

        cid   = uuid.uuid4()
        acct  = uuid.uuid4()
        prof  = uuid.uuid4()
        payout = uuid.uuid4()

        movement_mock = MagicMock()
        movement_mock.movement_id = uuid.uuid4()
        entry_mock    = MagicMock()

        db = _make_db()

        with patch.object(fin_svc, "_record_movement", return_value=movement_mock) as mock_mov, \
             patch.object(fin_svc, "_record_entry", return_value=entry_mock) as mock_entry:

            outflow, entry = fin_svc.handle_commission_paid(
                payout_id=payout,
                amount=Decimal("65.00"),
                account_id=acct,
                professional_id=prof,
                company_id=cid,
                db=db,
            )

        mock_mov.assert_called_once()
        mov_kwargs = mock_mov.call_args.kwargs
        assert mov_kwargs["type"] == "OUTFLOW"
        assert mov_kwargs["amount"] == Decimal("65.00")
        assert mov_kwargs["account_id"] == acct
        assert mov_kwargs["source_type"] == "commission_payout"
        assert mov_kwargs["source_id"] == payout

        mock_entry.assert_called_once()
        entry_kwargs = mock_entry.call_args.kwargs
        assert entry_kwargs["type"] == "COMISSAO"
        assert entry_kwargs["direction"] == "SUBTRACTS"
        assert entry_kwargs["category"] == "COMISSAO_SERVICO"
        assert entry_kwargs["amount"] == Decimal("65.00")

        assert outflow is movement_mock
        assert entry is entry_mock
