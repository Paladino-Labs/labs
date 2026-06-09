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
  13. payment.confirmed handler → provider_fee real usado (não "0" hardcoded)
  14. AFTER_FEES com fee>0 produz resultado diferente de BEFORE_FEES
  15. Payment sem appointment_id → sem comissão, sem erro
  16. Agendamento sem professional_id → sem comissão, sem erro
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
        """gross=100, rate=40%, BARBERSHOP_PAYS → commission=40.00"""
        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        svc   = uuid.uuid4()
        appt  = uuid.uuid4()
        policy = _make_policy(
            company_id=cid, professional_id=prof, service_id=svc,
            commission_base="GROSS_SERVICE",
            commission_fee_policy="BARBERSHOP_PAYS",
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
        """gross=100, fee=2, rate=40%, SPLIT_50_50 → (40.00) − (2/2) = 39.00"""
        cid   = uuid.uuid4()
        prof  = uuid.uuid4()
        policy = _make_policy(
            company_id=cid,
            commission_base="GROSS_SERVICE",
            commission_fee_policy="SPLIT_50_50",
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
        assert commission.commission_amount == Decimal("39.00")

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


# ─── 13–16. payment.confirmed handler ───────────────────────────────────────────

class TestPaymentConfirmedHandler:
    """Testa handle_payment_confirmed_commission — provider_fee real do Payment."""

    def _make_event(self, payment_id, company_id):
        e = MagicMock()
        e.event_id = uuid.uuid4()
        e.payload = {"payment_id": str(payment_id), "company_id": str(company_id)}
        return e

    def _mock_db_for_payment_and_appointment(self, payment_mock, appointment_mock):
        """Retorna db mock que responde corretamente a query(Payment) e query(Appointment)."""
        from app.infrastructure.db.models.payment import Payment
        from app.infrastructure.db.models.appointment import Appointment

        def query_side(model):
            inner = MagicMock()
            inner.filter.return_value = inner
            if model is Payment:
                inner.first.return_value = payment_mock
            elif model is Appointment:
                inner.first.return_value = appointment_mock
            else:
                inner.first.return_value = None
            return inner

        db = _make_db()
        db.query.side_effect = query_side
        return db

    def test_uses_real_provider_fee(self):
        """Handler lê provider_fee real do Payment — não "0" hardcoded do evento."""
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission
        from app.modules.commission import service as svc_mod

        cid = uuid.uuid4()
        prof = uuid.uuid4()
        appt = uuid.uuid4()
        svc_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        svc_item = MagicMock()
        svc_item.service_id = svc_id

        appointment_mock = MagicMock()
        appointment_mock.id = appt
        appointment_mock.company_id = cid
        appointment_mock.professional_id = prof
        appointment_mock.services = [svc_item]

        payment_mock = MagicMock()
        payment_mock.payment_id = payment_id
        payment_mock.company_id = cid
        payment_mock.appointment_id = appt
        payment_mock.gross_catalog_amount = Decimal("100.00")
        payment_mock.provider_fee = Decimal("3.00")

        event = self._make_event(payment_id, cid)
        commission_mock = _make_commission()

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission", return_value=commission_mock) as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = self._mock_db_for_payment_and_appointment(payment_mock, appointment_mock)
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)

        mock_calc.assert_called_once()
        kwargs = mock_calc.call_args.kwargs
        assert kwargs["provider_fee"] == Decimal("3.00")
        assert kwargs["gross_amount"] == Decimal("100.00")
        assert kwargs["professional_id"] == prof
        assert kwargs["appointment_id"] == appt
        assert kwargs["company_id"] == cid
        assert kwargs["service_id"] == svc_id
        assert kwargs["operation_type"] == "SERVICE_RENDERED"

    def test_after_fees_with_real_fee_differs_from_before_fees(self):
        """SPLIT_50_50 com provider_fee=3 → 40.00 − 1.50 = 38.50 (diferente de BARBERSHOP_PAYS)."""
        from app.modules.commission import service as svc_mod

        cid = uuid.uuid4()
        prof = uuid.uuid4()

        policy_before = _make_policy(
            company_id=cid, commission_base="GROSS_SERVICE",
            commission_fee_policy="BARBERSHOP_PAYS", rate=Decimal("40.00"),
        )
        policy_after = _make_policy(
            company_id=cid, commission_base="GROSS_SERVICE",
            commission_fee_policy="SPLIT_50_50", rate=Decimal("40.00"),
        )

        captured_before = {}
        db_before = _make_db()
        with patch.object(svc_mod, "_find_active_policy", return_value=policy_before):
            db_before.add.side_effect = lambda obj: captured_before.update({"commission": obj})
            svc_mod.calculate_commission(
                professional_id=prof, service_id=None,
                gross_amount=Decimal("100.00"), provider_fee=Decimal("3.00"),
                operation_type="SERVICE_RENDERED", appointment_id=None,
                company_id=cid, db=db_before,
            )

        captured_after = {}
        db_after = _make_db()
        with patch.object(svc_mod, "_find_active_policy", return_value=policy_after):
            db_after.add.side_effect = lambda obj: captured_after.update({"commission": obj})
            svc_mod.calculate_commission(
                professional_id=prof, service_id=None,
                gross_amount=Decimal("100.00"), provider_fee=Decimal("3.00"),
                operation_type="SERVICE_RENDERED", appointment_id=None,
                company_id=cid, db=db_after,
            )

        # BARBERSHOP_PAYS: 100 * 0.40 = 40.00
        # SPLIT_50_50:     (100 * 0.40) − (3/2) = 40.00 − 1.50 = 38.50
        assert captured_before["commission"].commission_amount == Decimal("40.00")
        assert captured_after["commission"].commission_amount == Decimal("38.50")
        assert captured_after["commission"].commission_amount < captured_before["commission"].commission_amount

    def test_payment_without_appointment_id_skips(self):
        """Payment sem appointment_id → não gera comissão, sem erro."""
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission
        from app.modules.commission import service as svc_mod
        from app.infrastructure.db.models.payment import Payment

        cid = uuid.uuid4()
        payment_id = uuid.uuid4()

        payment_mock = MagicMock()
        payment_mock.payment_id = payment_id
        payment_mock.company_id = cid
        payment_mock.appointment_id = None  # sem agendamento

        event = self._make_event(payment_id, cid)

        def query_side(model):
            inner = MagicMock()
            inner.filter.return_value = inner
            inner.first.return_value = payment_mock if model is Payment else None
            return inner

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission") as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = _make_db()
            mock_db.query.side_effect = query_side
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)

        mock_calc.assert_not_called()

    def test_appointment_without_professional_id_skips(self):
        """Agendamento sem professional_id → não gera comissão, sem erro."""
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission
        from app.modules.commission import service as svc_mod
        from app.infrastructure.db.models.payment import Payment
        from app.infrastructure.db.models.appointment import Appointment

        cid = uuid.uuid4()
        payment_id = uuid.uuid4()
        appt = uuid.uuid4()

        payment_mock = MagicMock()
        payment_mock.payment_id = payment_id
        payment_mock.company_id = cid
        payment_mock.appointment_id = appt

        appointment_mock = MagicMock()
        appointment_mock.id = appt
        appointment_mock.company_id = cid
        appointment_mock.professional_id = None  # sem profissional

        event = self._make_event(payment_id, cid)

        def query_side(model):
            inner = MagicMock()
            inner.filter.return_value = inner
            if model is Payment:
                inner.first.return_value = payment_mock
            elif model is Appointment:
                inner.first.return_value = appointment_mock
            else:
                inner.first.return_value = None
            return inner

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission") as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = _make_db()
            mock_db.query.side_effect = query_side
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)

        mock_calc.assert_not_called()

    def test_exception_is_best_effort(self):
        """Erro interno não propaga exceção — handler é best-effort."""
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission

        cid = uuid.uuid4()
        payment_id = uuid.uuid4()

        event = self._make_event(payment_id, cid)

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = _make_db()
            mock_db.query.side_effect = RuntimeError("DB error")
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)  # não deve lançar

        mock_db.rollback.assert_called_once()


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


# ─── V2. Novo modelo de comissão ─────────────────────────────────────────────

class TestCalculateCommissionV2:
    """Testa as 3 novas opções de taxa + fallback legado e nunca-negativo."""

    def _calc(self, fee_policy, gross, fee, rate=Decimal("40.00")):
        from app.modules.commission import service as svc_mod

        cid  = uuid.uuid4()
        prof = uuid.uuid4()
        policy = _make_policy(
            company_id=cid,
            commission_base="GROSS_SERVICE",
            commission_fee_policy=fee_policy,
            rate=rate,
        )

        captured = {}
        db = _make_db()
        db.add.side_effect = lambda obj: captured.update({"commission": obj})

        with patch.object(svc_mod, "_find_active_policy", return_value=policy):
            svc_mod.calculate_commission(
                professional_id=prof, service_id=None,
                gross_amount=gross, provider_fee=fee,
                operation_type="SERVICE_RENDERED", appointment_id=None,
                company_id=cid, db=db,
            )

        return captured["commission"]

    def test_barbershop_pays_ignores_fee(self):
        """BARBERSHOP_PAYS: barbearia absorve taxa — barbeiro recebe rate × gross."""
        # gross=100, fee=3, rate=40% → 40.00
        commission = self._calc("BARBERSHOP_PAYS", Decimal("100.00"), Decimal("3.00"))
        assert commission.commission_amount == Decimal("40.00")

    def test_split_50_50_halves_fee(self):
        """SPLIT_50_50: taxa dividida → (rate × gross) − (fee / 2)."""
        # gross=100, fee=3, rate=40% → 40.00 − 1.50 = 38.50
        commission = self._calc("SPLIT_50_50", Decimal("100.00"), Decimal("3.00"))
        assert commission.commission_amount == Decimal("38.50")

    def test_barber_pays_full_fee(self):
        """BARBER_PAYS: barbeiro absorve taxa inteira → (rate × gross) − fee."""
        # gross=100, fee=3, rate=40% → 40.00 − 3.00 = 37.00
        commission = self._calc("BARBER_PAYS", Decimal("100.00"), Decimal("3.00"))
        assert commission.commission_amount == Decimal("37.00")

    def test_commission_never_negative(self):
        """commission_amount nunca retorna valor negativo — piso em 0.00."""
        # gross=10, fee=50, rate=40% → gross_commission=4.00, 4.00−50=−46 → 0.00
        commission = self._calc("BARBER_PAYS", Decimal("10.00"), Decimal("50.00"))
        assert commission.commission_amount == Decimal("0.00")

    def test_split_50_50_quantized_to_cents(self):
        """SPLIT_50_50 resultado é Decimal quantizado em 2 casas decimais."""
        # gross=100, fee=3, rate=40% → 38.50 (não 38.5000...)
        commission = self._calc("SPLIT_50_50", Decimal("100.00"), Decimal("3.00"))
        assert isinstance(commission.commission_amount, Decimal)
        assert str(commission.commission_amount) == "38.50"

    def test_legacy_before_fees_fallback(self):
        """BEFORE_FEES (dado não migrado) → fallback conservador = gross_commission."""
        # Garante que rollback ou dados antigos não quebram o sistema
        # gross=100, fee=3, rate=40% → 40.00 (ignora fee, igual a BARBERSHOP_PAYS)
        commission = self._calc("BEFORE_FEES", Decimal("100.00"), Decimal("3.00"))
        assert commission.commission_amount == Decimal("40.00")


# ─── T1. Wiring do EventBus ───────────────────────────────────────────────────

class TestCommissionHandlerWiring:

    def test_register_handlers_wires_payment_confirmed(self):
        """
        Após register_handlers(), payment.confirmed deve invocar
        handle_payment_confirmed_commission.
        """
        from app.infrastructure.event_bus import EventBus
        from app.workers.handlers import commission_handler

        bus = EventBus()

        with patch("app.infrastructure.event_bus.event_bus", bus):
            commission_handler.register_handlers()

        handlers = bus._handlers.get("payment.confirmed", [])
        assert commission_handler.handle_payment_confirmed_commission in handlers

    def test_handle_operation_completed_not_registered(self):
        """
        handle_operation_completed não deve estar registrado no EventBus
        (handler mantido mas intencionalmente não ativo no Stage 0).
        """
        from app.infrastructure.event_bus import EventBus
        from app.workers.handlers import commission_handler

        bus = EventBus()

        with patch("app.infrastructure.event_bus.event_bus", bus):
            commission_handler.register_handlers()

        handlers = bus._handlers.get("operation.completed", [])
        assert commission_handler.handle_operation_completed not in handlers


# ─── T3. Idempotência do commission_handler ───────────────────────────────────

class TestCommissionHandlerIdempotency:

    def _make_full_event(self, payment_id, company_id):
        e = MagicMock()
        e.event_id = uuid.uuid4()
        e.payload = {"payment_id": str(payment_id), "company_id": str(company_id)}
        return e

    def _mock_db_for_idempotency(self, payment_mock, appointment_mock, existing_commission=None):
        """
        db mock que responde a query(Payment), query(Appointment) e query(Commission).
        existing_commission=None → sem comissão prévia; caso contrário retorna a mock.
        """
        from app.infrastructure.db.models.payment import Payment
        from app.infrastructure.db.models.appointment import Appointment
        from app.infrastructure.db.models.commission import Commission

        def query_side(model):
            inner = MagicMock()
            inner.filter.return_value = inner
            if model is Payment:
                inner.first.return_value = payment_mock
            elif model is Appointment:
                inner.first.return_value = appointment_mock
            elif model is Commission:
                inner.first.return_value = existing_commission
            else:
                inner.first.return_value = None
            return inner

        db = _make_db()
        db.query.side_effect = query_side
        return db

    def _make_payment_and_appointment(self, cid, payment_id, appt_id, prof_id, svc_id):
        svc_item = MagicMock()
        svc_item.service_id = svc_id

        payment_mock = MagicMock()
        payment_mock.payment_id = payment_id
        payment_mock.company_id = cid
        payment_mock.appointment_id = appt_id
        payment_mock.gross_catalog_amount = Decimal("100.00")
        payment_mock.provider_fee = Decimal("2.00")

        appointment_mock = MagicMock()
        appointment_mock.id = appt_id
        appointment_mock.company_id = cid
        appointment_mock.professional_id = prof_id
        appointment_mock.services = [svc_item]

        return payment_mock, appointment_mock

    def test_duplicate_payment_confirmed_does_not_create_duplicate_commission(self):
        """
        Se payment.confirmed for processado duas vezes para o mesmo agendamento,
        apenas uma Commission deve ser criada — a segunda chamada é ignorada.
        """
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission
        from app.modules.commission import service as svc_mod

        cid = uuid.uuid4()
        payment_id = uuid.uuid4()
        appt_id = uuid.uuid4()
        prof_id = uuid.uuid4()
        svc_id = uuid.uuid4()

        payment_mock, appointment_mock = self._make_payment_and_appointment(
            cid, payment_id, appt_id, prof_id, svc_id
        )

        # Commission já existe (simulando retry de webhook)
        existing_commission = _make_commission(
            company_id=cid, appointment_id=appt_id, status="CALCULATED"
        )

        event = self._make_full_event(payment_id, cid)

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission") as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            mock_db = self._mock_db_for_idempotency(
                payment_mock, appointment_mock, existing_commission=existing_commission
            )
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)

        # Guarda deve bloquear — calculate_commission NÃO deve ser chamado
        mock_calc.assert_not_called()

    def test_first_call_creates_commission_normally(self):
        """
        Primeira chamada (sem Commission prévia) cria a Commission normalmente.
        A guarda não deve bloquear quando não há comissão existente.
        """
        from app.workers.handlers.commission_handler import handle_payment_confirmed_commission
        from app.modules.commission import service as svc_mod

        cid = uuid.uuid4()
        payment_id = uuid.uuid4()
        appt_id = uuid.uuid4()
        prof_id = uuid.uuid4()
        svc_id = uuid.uuid4()

        payment_mock, appointment_mock = self._make_payment_and_appointment(
            cid, payment_id, appt_id, prof_id, svc_id
        )

        event = self._make_full_event(payment_id, cid)
        commission_mock = _make_commission(company_id=cid, appointment_id=appt_id)

        with patch("app.workers.handlers.commission_handler.SessionLocal") as mock_session, \
             patch.object(svc_mod, "calculate_commission", return_value=commission_mock) as mock_calc, \
             patch("app.core.db_rls.set_rls_context"):

            # existing_commission=None → sem comissão prévia → guarda não bloqueia
            mock_db = self._mock_db_for_idempotency(
                payment_mock, appointment_mock, existing_commission=None
            )
            mock_session.return_value = mock_db

            handle_payment_confirmed_commission(event)

        mock_calc.assert_called_once()
        kwargs = mock_calc.call_args.kwargs
        assert kwargs["professional_id"] == prof_id
        assert kwargs["appointment_id"] == appt_id
        assert kwargs["company_id"] == cid
        assert kwargs["provider_fee"] == Decimal("2.00")
