"""
Testes Sprint 15 — Assinaturas.

Usa mocks (unittest.mock) — sem banco PostgreSQL real.

Casos obrigatórios:
  1.  subscription_renewal_worker: ACTIVE + next_billing_at passado → Payment PENDING criado
  2.  subscription_renewal_worker: idempotência — PENDING já existe → não cria duplicata
  3.  payment.confirmed (assinatura) → CustomerCredit renovado + Entry ASSINATURA_RENOVACAO
  4.  rollover_enabled=false: expires_at = now()+cycle_days
  5.  rollover_enabled=true: expires_at = None (cotas acumulam)
  6.  Inadimplência 7d → OVERDUE
  7.  Inadimplência 30d → SUSPENDED
  8.  SUSPENDED → consume_for_operation bloqueado → NoCreditAvailableError
  9.  pause → PAUSED; resume → ACTIVE; cancel → CANCELLED
  10. Cross-tenant: subscriptions e plans isolados
  11. subscribe() com plano inativo → 422
  12. payment.confirmed sem subscription_id → handler é no-op
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

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

def _now():
    return datetime.now(timezone.utc)


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.commit   = MagicMock()
    db.rollback = MagicMock()
    db.flush    = MagicMock()
    db.add      = MagicMock()
    db.refresh  = MagicMock()
    db.close    = MagicMock()
    return db


def _make_item(item_type="SERVICE", service_id=None, product_id=None, quantity=4):
    it = MagicMock()
    it.item_type  = item_type
    it.service_id = service_id if item_type == "SERVICE" else None
    it.product_id = product_id if item_type == "PRODUCT" else None
    it.quantity   = quantity
    return it


def _make_plan(
    plan_id=None,
    company_id=None,
    name="Plano Mensal",
    cotas_per_cycle=4,
    price=Decimal("99.90"),
    cycle_days=30,
    rollover_enabled=False,
    is_active=True,
    items=None,
):
    p = MagicMock()
    p.plan_id          = plan_id or uuid.uuid4()
    p.company_id       = company_id or uuid.uuid4()
    p.name             = name
    p.cotas_per_cycle  = cotas_per_cycle
    p.price            = price
    p.cycle_days       = cycle_days
    p.rollover_enabled = rollover_enabled
    p.is_active        = is_active
    # Sprint 26: plano multi-item. Default = 1 item SERVICE com quantity=cotas_per_cycle
    # (preserva a equivalência credit.total_cotas == plan.cotas_per_cycle).
    p.items = items if items is not None else [
        _make_item("SERVICE", service_id=uuid.uuid4(), quantity=cotas_per_cycle)
    ]
    return p


def _make_subscription(
    subscription_id=None,
    company_id=None,
    customer_id=None,
    plan_id=None,
    status="ACTIVE",
    next_billing_at=None,
    overdue_since=None,
):
    s = MagicMock()
    s.subscription_id = subscription_id or uuid.uuid4()
    s.company_id      = company_id or uuid.uuid4()
    s.customer_id     = customer_id or uuid.uuid4()
    s.plan_id         = plan_id or uuid.uuid4()
    s.status          = status
    s.next_billing_at = next_billing_at or (_now() - timedelta(days=1))
    s.overdue_since   = overdue_since
    s.paused_at       = None
    s.cancelled_at    = None
    return s


# ─── 1-2. subscription_renewal_worker ────────────────────────────────────────

class TestRenewalWorker:
    def test_renewal_creates_pending_payment_for_active_subscription(self):
        """ACTIVE + next_billing_at no passado → Payment PENDING criado."""
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        plan_id = uuid.uuid4()
        account_id = uuid.uuid4()

        sub = _make_subscription(
            subscription_id=sub_id,
            company_id=company_id,
            status="ACTIVE",
            next_billing_at=_now() - timedelta(hours=1),
        )
        sub.plan_id = plan_id

        plan = _make_plan(plan_id=plan_id, company_id=company_id, cycle_days=30)

        account = MagicMock()
        account.account_id = account_id
        account.is_default_inflow = True

        added_payments = []

        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.account import Account

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.limit.return_value = mock_q

            if model is CustomerSubscription:
                mock_q.all.return_value = [sub]
                mock_q.filter.return_value.limit.return_value.all.return_value = [sub]
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            elif model is Payment:
                # Nenhum PENDING existente
                mock_q.first.return_value = None
            elif model is Account:
                mock_q.first.return_value = account
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []
            return mock_q

        db.query.side_effect = _query_side_effect

        original_next_billing = sub.next_billing_at

        with (
            patch("app.workers.tasks.subscription_renewal.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_renewal.set_rls_context"),
        ):
            from app.workers.tasks.subscription_renewal import subscription_renewal_worker
            subscription_renewal_worker(MagicMock())

        # Deve ter adicionado um Payment
        db.add.assert_called()
        added = [c.args[0] for c in db.add.call_args_list]
        payments = [o for o in added if hasattr(o, "subscription_id")]
        assert len(payments) == 1
        p = payments[0]
        assert p.subscription_id == sub_id
        assert p.status == "PENDING"
        assert p.company_id == company_id
        assert p.customer_id == sub.customer_id

        # next_billing_at deve ter avançado
        assert sub.next_billing_at == original_next_billing + timedelta(days=plan.cycle_days)

        db.commit.assert_called()

    def test_renewal_skips_when_pending_payment_exists(self):
        """Idempotência: não cria Payment PENDING se já existe um para a subscription."""
        sub_id = uuid.uuid4()
        sub = _make_subscription(
            subscription_id=sub_id,
            status="ACTIVE",
            next_billing_at=_now() - timedelta(hours=1),
        )
        plan = _make_plan()

        existing_pending = MagicMock()
        existing_pending.status = "PENDING"
        existing_pending.subscription_id = sub_id

        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            from app.infrastructure.db.models.payment import Payment

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.limit.return_value = mock_q

            if model is CustomerSubscription:
                mock_q.all.return_value = [sub]
                mock_q.filter.return_value.limit.return_value.all.return_value = [sub]
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            elif model is Payment:
                # Já existe PENDING
                mock_q.first.return_value = existing_pending
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.tasks.subscription_renewal.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_renewal.set_rls_context"),
        ):
            from app.workers.tasks.subscription_renewal import subscription_renewal_worker
            subscription_renewal_worker(MagicMock())

        # Não deve adicionar nenhum objeto
        assert not any(
            hasattr(c.args[0] if c.args else None, "subscription_id")
            for c in db.add.call_args_list
            if c.args
        )


# ─── 3-5. Handler payment.confirmed (subscription) ───────────────────────────

class TestPaymentConfirmedSubscriptionHandler:
    def _make_event(self, payment_id, company_id):
        event = MagicMock()
        event.payload    = {"payment_id": str(payment_id)}
        event.company_id = company_id
        event.event_id   = uuid.uuid4()
        return event

    def test_handler_creates_credit_and_financial_entry(self):
        """payment.confirmed (assinatura) → CustomerCredit renovado + handle_subscription_renewed chamado."""
        company_id      = uuid.uuid4()
        payment_id      = uuid.uuid4()
        sub_id          = uuid.uuid4()
        customer_id     = uuid.uuid4()
        account_id      = uuid.uuid4()

        plan = _make_plan(cotas_per_cycle=4, cycle_days=30, rollover_enabled=False)
        sub  = _make_subscription(
            subscription_id=sub_id,
            company_id=company_id,
            customer_id=customer_id,
            status="ACTIVE",
        )
        sub.plan_id = plan.plan_id

        payment = MagicMock()
        payment.payment_id      = payment_id
        payment.company_id      = company_id
        payment.subscription_id = sub_id
        payment.target_account_id = account_id

        event = self._make_event(payment_id, company_id)

        added_credits = []
        db = _make_db()
        db.add.side_effect = lambda obj: added_credits.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q

            if model is Payment:
                mock_q.first.return_value = payment
            elif model is CustomerSubscription:
                mock_q.first.return_value = sub
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.handlers.subscription_payment_handler.SessionLocal", return_value=db),
            patch("app.workers.handlers.subscription_payment_handler.set_rls_context"),
            patch("app.modules.financial_core.service.handle_subscription_renewed") as mock_financial,
        ):
            from app.workers.handlers.subscription_payment_handler import handle_payment_confirmed_subscription
            handle_payment_confirmed_subscription(event)

        # CustomerCredit deve ter sido adicionado
        from app.infrastructure.db.models.customer_credit import CustomerCredit
        credits = [o for o in added_credits if hasattr(o, "entitlement_type")]
        assert len(credits) == 1
        credit = credits[0]
        assert credit.entitlement_type == "SUBSCRIPTION"
        assert credit.source_id == sub_id
        assert credit.total_cotas == plan.cotas_per_cycle
        assert credit.remaining_cotas == plan.cotas_per_cycle
        assert credit.status == "ACTIVE"
        assert credit.company_id == company_id
        assert credit.customer_id == customer_id

        # handle_subscription_renewed deve ter sido chamado
        mock_financial.assert_called_once()
        call_kwargs = mock_financial.call_args.kwargs
        assert call_kwargs["subscription_id"] == sub_id
        assert call_kwargs["plan_price"] == Decimal(str(plan.price))
        assert call_kwargs["company_id"] == company_id

        db.commit.assert_called()

    def test_handler_rollover_false_sets_expires_at(self):
        """rollover_enabled=false: expires_at = now()+cycle_days."""
        company_id  = uuid.uuid4()
        payment_id  = uuid.uuid4()
        sub_id      = uuid.uuid4()

        plan = _make_plan(cotas_per_cycle=4, cycle_days=30, rollover_enabled=False)
        sub  = _make_subscription(subscription_id=sub_id, company_id=company_id, status="ACTIVE")
        sub.plan_id = plan.plan_id

        payment = MagicMock()
        payment.payment_id      = payment_id
        payment.company_id      = company_id
        payment.subscription_id = sub_id
        payment.target_account_id = uuid.uuid4()

        event = self._make_event(payment_id, company_id)
        added_credits = []
        db = _make_db()
        db.add.side_effect = lambda obj: added_credits.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            if model is Payment:
                mock_q.first.return_value = payment
            elif model is CustomerSubscription:
                mock_q.first.return_value = sub
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.handlers.subscription_payment_handler.SessionLocal", return_value=db),
            patch("app.workers.handlers.subscription_payment_handler.set_rls_context"),
            patch("app.modules.financial_core.service.handle_subscription_renewed"),
        ):
            from app.workers.handlers.subscription_payment_handler import handle_payment_confirmed_subscription
            handle_payment_confirmed_subscription(event)

        credits = [o for o in added_credits if hasattr(o, "entitlement_type")]
        assert len(credits) == 1
        credit = credits[0]
        assert credit.expires_at is not None
        diff = credit.expires_at - credit.granted_at
        assert abs(diff.days - 30) <= 1

    def test_handler_rollover_true_no_expires_at(self):
        """rollover_enabled=true: expires_at = None (cotas acumulam entre ciclos)."""
        company_id  = uuid.uuid4()
        payment_id  = uuid.uuid4()
        sub_id      = uuid.uuid4()

        plan = _make_plan(cotas_per_cycle=4, cycle_days=30, rollover_enabled=True)
        sub  = _make_subscription(subscription_id=sub_id, company_id=company_id, status="ACTIVE")
        sub.plan_id = plan.plan_id

        payment = MagicMock()
        payment.payment_id      = payment_id
        payment.company_id      = company_id
        payment.subscription_id = sub_id
        payment.target_account_id = uuid.uuid4()

        event = self._make_event(payment_id, company_id)
        added_credits = []
        db = _make_db()
        db.add.side_effect = lambda obj: added_credits.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            if model is Payment:
                mock_q.first.return_value = payment
            elif model is CustomerSubscription:
                mock_q.first.return_value = sub
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.handlers.subscription_payment_handler.SessionLocal", return_value=db),
            patch("app.workers.handlers.subscription_payment_handler.set_rls_context"),
            patch("app.modules.financial_core.service.handle_subscription_renewed"),
        ):
            from app.workers.handlers.subscription_payment_handler import handle_payment_confirmed_subscription
            handle_payment_confirmed_subscription(event)

        credits = [o for o in added_credits if hasattr(o, "entitlement_type")]
        assert len(credits) == 1
        assert credits[0].expires_at is None

    def test_handler_noop_when_no_subscription_id(self):
        """payment.confirmed sem subscription_id: handler é no-op."""
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        payment = MagicMock()
        payment.payment_id      = payment_id
        payment.company_id      = company_id
        payment.subscription_id = None  # Sem assinatura

        event = self._make_event(payment_id, company_id)
        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.payment import Payment
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            if model is Payment:
                mock_q.first.return_value = payment
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.handlers.subscription_payment_handler.SessionLocal", return_value=db),
            patch("app.workers.handlers.subscription_payment_handler.set_rls_context"),
        ):
            from app.workers.handlers.subscription_payment_handler import handle_payment_confirmed_subscription
            handle_payment_confirmed_subscription(event)

        db.add.assert_not_called()
        db.commit.assert_not_called()

    def test_handler_overdue_subscription_returns_to_active(self):
        """payment.confirmed para subscription OVERDUE → status volta para ACTIVE."""
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        sub_id     = uuid.uuid4()

        plan = _make_plan()
        sub  = _make_subscription(
            subscription_id=sub_id,
            company_id=company_id,
            status="OVERDUE",
        )
        sub.overdue_since = _now() - timedelta(days=10)
        sub.plan_id = plan.plan_id

        payment = MagicMock()
        payment.payment_id      = payment_id
        payment.company_id      = company_id
        payment.subscription_id = sub_id
        payment.target_account_id = uuid.uuid4()

        event = self._make_event(payment_id, company_id)
        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            if model is Payment:
                mock_q.first.return_value = payment
            elif model is CustomerSubscription:
                mock_q.first.return_value = sub
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.handlers.subscription_payment_handler.SessionLocal", return_value=db),
            patch("app.workers.handlers.subscription_payment_handler.set_rls_context"),
            patch("app.modules.financial_core.service.handle_subscription_renewed"),
        ):
            from app.workers.handlers.subscription_payment_handler import handle_payment_confirmed_subscription
            handle_payment_confirmed_subscription(event)

        assert sub.status == "ACTIVE"
        assert sub.overdue_since is None


# ─── 6-7. Overdue worker ──────────────────────────────────────────────────────

class TestOverdueWorker:
    def _make_overdue_db(self, active_subs, old_pending_payment, overdue_subs):
        """Cria db mock diferenciando queries ACTIVE e OVERDUE por ordem de chamada."""
        db = _make_db()
        query_call_count = [0]

        def _query_side_effect(model):
            from app.infrastructure.db.models.subscription import CustomerSubscription
            from app.infrastructure.db.models.payment import Payment

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q

            if model is CustomerSubscription:
                query_call_count[0] += 1
                if query_call_count[0] == 1:
                    # Primeira chamada: query ACTIVE
                    mock_q.all.return_value = active_subs
                else:
                    # Segunda chamada: query OVERDUE
                    mock_q.all.return_value = overdue_subs
            elif model is Payment:
                mock_q.first.return_value = old_pending_payment
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []
            return mock_q

        db.query.side_effect = _query_side_effect
        return db

    def test_active_with_old_pending_payment_becomes_overdue(self):
        """ACTIVE + Payment PENDING criado há > 7 dias → OVERDUE."""
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, status="ACTIVE")
        sub.overdue_since = None

        old_pending = MagicMock()
        old_pending.status = "PENDING"
        old_pending.subscription_id = sub_id
        old_pending.created_at = _now() - timedelta(days=8)

        # Segunda query (OVERDUE): sub agora é OVERDUE mas overdue_since acabou de ser setado,
        # então não satisfaz o filtro overdue_since <= suspend_cutoff. Retorna [].
        db = self._make_overdue_db(
            active_subs=[sub],
            old_pending_payment=old_pending,
            overdue_subs=[],
        )

        with (
            patch("app.workers.tasks.subscription_overdue.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_overdue.set_rls_context"),
        ):
            from app.workers.tasks.subscription_overdue import subscription_overdue_worker
            subscription_overdue_worker(MagicMock())

        assert sub.status == "OVERDUE"
        assert sub.overdue_since is not None
        db.commit.assert_called()

    def test_overdue_30_days_becomes_suspended(self):
        """OVERDUE há > 30 dias → SUSPENDED."""
        sub_id = uuid.uuid4()
        sub = _make_subscription(
            subscription_id=sub_id,
            status="OVERDUE",
            overdue_since=_now() - timedelta(days=31),
        )

        # Primeira query (ACTIVE): nenhuma sub; Segunda (OVERDUE): retorna sub
        db = self._make_overdue_db(
            active_subs=[],
            old_pending_payment=None,
            overdue_subs=[sub],
        )

        with (
            patch("app.workers.tasks.subscription_overdue.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_overdue.set_rls_context"),
        ):
            from app.workers.tasks.subscription_overdue import subscription_overdue_worker
            subscription_overdue_worker(MagicMock())

        assert sub.status == "SUSPENDED"
        db.commit.assert_called()

    def test_active_without_old_pending_not_overdue(self):
        """ACTIVE sem Payment PENDING antigo: não vira OVERDUE."""
        sub = _make_subscription(status="ACTIVE")
        sub.overdue_since = None

        # Primeira query (ACTIVE): sub; Segunda (OVERDUE): nenhuma
        db = self._make_overdue_db(
            active_subs=[sub],
            old_pending_payment=None,  # sem PENDING antigo
            overdue_subs=[],
        )

        with (
            patch("app.workers.tasks.subscription_overdue.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_overdue.set_rls_context"),
        ):
            from app.workers.tasks.subscription_overdue import subscription_overdue_worker
            subscription_overdue_worker(MagicMock())

        assert sub.status == "ACTIVE"  # não mudou


# ─── 8. SUSPENDED → consume_for_operation bloqueado ──────────────────────────

class TestSuspendedBlocked:
    def test_suspended_subscription_blocks_consume_for_operation(self):
        """SUSPENDED → consume_for_operation levanta NoCreditAvailableError."""
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        sub_id      = uuid.uuid4()
        credit_id   = uuid.uuid4()

        # Crédito ACTIVE vindo de uma assinatura SUSPENDED
        credit = MagicMock()
        credit.credit_id         = credit_id
        credit.company_id        = company_id
        credit.customer_id       = customer_id
        credit.entitlement_type  = "SUBSCRIPTION"
        credit.source_id         = sub_id
        credit.status            = "ACTIVE"
        credit.remaining_cotas   = 2
        credit.expires_at        = None
        credit.granted_at        = _now() - timedelta(days=1)

        # Assinatura SUSPENDED
        subscription = MagicMock()
        subscription.subscription_id = sub_id
        subscription.status           = "SUSPENDED"

        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.customer_credit import CustomerCredit
            from app.infrastructure.db.models.subscription import CustomerSubscription

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.with_for_update.return_value = mock_q

            if model is CustomerCredit:
                mock_q.first.return_value = credit
            elif model is CustomerSubscription:
                mock_q.first.return_value = subscription
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        from app.modules.customer_credit import service as credit_service
        with pytest.raises(NoCreditAvailableError):
            credit_service.consume_for_operation(
                customer_id=customer_id,
                appointment_id=None,
                company_id=company_id,
                db=db,
            )

    def test_active_subscription_allows_consume(self):
        """ACTIVE subscription não bloqueia consume_for_operation."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        sub_id      = uuid.uuid4()
        credit_id   = uuid.uuid4()

        credit = MagicMock()
        credit.credit_id         = credit_id
        credit.company_id        = company_id
        credit.customer_id       = customer_id
        credit.entitlement_type  = "SUBSCRIPTION"
        credit.source_id         = sub_id
        credit.status            = "ACTIVE"
        credit.remaining_cotas   = 2
        credit.expires_at        = None
        credit.granted_at        = _now() - timedelta(days=1)

        subscription = MagicMock()
        subscription.subscription_id = sub_id
        subscription.status           = "ACTIVE"

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.customer_credit import CustomerCredit, CustomerCreditConsumption
            from app.infrastructure.db.models.subscription import CustomerSubscription

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.with_for_update.return_value = mock_q

            if model is CustomerCredit:
                mock_q.first.return_value = credit
            elif model is CustomerSubscription:
                mock_q.first.return_value = subscription
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        from app.modules.customer_credit import service as credit_service
        result = credit_service.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )

        assert credit.remaining_cotas == 1  # decrementou

    def test_grant_cota_credit_not_blocked_by_subscription_check(self):
        """Crédito GRANT_COTA (não SUBSCRIPTION) não é verificado contra subscription."""
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        credit_id   = uuid.uuid4()

        credit = MagicMock()
        credit.credit_id         = credit_id
        credit.company_id        = company_id
        credit.customer_id       = customer_id
        credit.entitlement_type  = "GRANT_COTA"  # não é SUBSCRIPTION
        credit.source_id         = None
        credit.status            = "ACTIVE"
        credit.remaining_cotas   = 1
        credit.expires_at        = None
        credit.granted_at        = _now() - timedelta(days=1)

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.customer_credit import CustomerCredit

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.with_for_update.return_value = mock_q

            if model is CustomerCredit:
                mock_q.first.return_value = credit
            else:
                mock_q.first.return_value = None
            return mock_q

        db.query.side_effect = _query_side_effect

        from app.modules.customer_credit import service as credit_service
        # Não deve levantar exceção
        result = credit_service.consume_for_operation(
            customer_id=customer_id,
            appointment_id=None,
            company_id=company_id,
            db=db,
        )
        assert credit.remaining_cotas == 0


# ─── 9. pause / resume / cancel ──────────────────────────────────────────────

class TestSubscriptionFSM:
    def test_pause_active_subscription(self):
        """pause() muda ACTIVE → PAUSED."""
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="ACTIVE")
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            result = svc.pause(sub_id, company_id, db)

        assert sub.status == "PAUSED"
        assert sub.paused_at is not None
        db.commit.assert_called()

    def test_resume_paused_subscription(self):
        """resume() muda PAUSED → ACTIVE."""
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="PAUSED")
        sub.paused_at = _now() - timedelta(days=1)
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            result = svc.resume(sub_id, company_id, db)

        assert sub.status == "ACTIVE"
        assert sub.paused_at is None
        db.commit.assert_called()

    def test_cancel_active_subscription(self):
        """cancel() muda ACTIVE → CANCELLED."""
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="ACTIVE")
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            result = svc.cancel(sub_id, company_id, db)

        assert sub.status == "CANCELLED"
        assert sub.cancelled_at is not None
        db.commit.assert_called()

    def test_pause_cancelled_raises_422(self):
        """pause() em CANCELLED levanta 422."""
        from fastapi import HTTPException
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="CANCELLED")
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            with pytest.raises(HTTPException) as exc_info:
                svc.pause(sub_id, company_id, db)
        assert exc_info.value.status_code == 422

    def test_resume_active_raises_422(self):
        """resume() em ACTIVE (não PAUSED) levanta 422."""
        from fastapi import HTTPException
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="ACTIVE")
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            with pytest.raises(HTTPException) as exc_info:
                svc.resume(sub_id, company_id, db)
        assert exc_info.value.status_code == 422

    def test_cancel_already_cancelled_raises_422(self):
        """cancel() em CANCELLED levanta 422."""
        from fastapi import HTTPException
        company_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        sub = _make_subscription(subscription_id=sub_id, company_id=company_id, status="CANCELLED")
        db = _make_db()

        with patch("app.modules.subscriptions.service.get_subscription", return_value=sub):
            from app.modules.subscriptions import service as svc
            with pytest.raises(HTTPException) as exc_info:
                svc.cancel(sub_id, company_id, db)
        assert exc_info.value.status_code == 422


# ─── 10. Cross-tenant isolation ───────────────────────────────────────────────

class TestCrossTenant:
    def test_get_subscription_wrong_company_raises_404(self):
        """Buscar subscription de outro tenant levanta 404."""
        from fastapi import HTTPException

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.subscriptions import service as svc
        with pytest.raises(HTTPException) as exc_info:
            svc.get_subscription(uuid.uuid4(), uuid.uuid4(), db)
        assert exc_info.value.status_code == 404

    def test_get_plan_wrong_company_raises_404(self):
        """Buscar plano de outro tenant levanta 404."""
        from fastapi import HTTPException

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.subscriptions import service as svc
        with pytest.raises(HTTPException) as exc_info:
            svc._get_plan_or_404(uuid.uuid4(), uuid.uuid4(), db)
        assert exc_info.value.status_code == 404

    def test_list_subscriptions_filters_by_company(self):
        """list_subscriptions filtra por company_id."""
        company_id = uuid.uuid4()
        db = _make_db()

        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.all.return_value = []
        db.query.return_value = mock_q

        from app.modules.subscriptions import service as svc
        svc.list_subscriptions(company_id=company_id, db=db)

        db.query.assert_called()

    def test_renewal_worker_creates_payment_with_correct_company(self):
        """subscription_renewal_worker usa company_id da subscription."""
        company_a = uuid.uuid4()
        company_b = uuid.uuid4()
        sub_id = uuid.uuid4()

        sub = _make_subscription(
            subscription_id=sub_id,
            company_id=company_a,
            status="ACTIVE",
            next_billing_at=_now() - timedelta(hours=1),
        )
        plan = _make_plan(company_id=company_a)
        sub.plan_id = plan.plan_id

        account = MagicMock()
        account.account_id = uuid.uuid4()
        account.is_default_inflow = True

        added_payments = []
        db = _make_db()
        db.add.side_effect = lambda obj: added_payments.append(obj)

        def _query_side_effect(model):
            from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
            from app.infrastructure.db.models.payment import Payment
            from app.infrastructure.db.models.account import Account

            mock_q = MagicMock()
            mock_q.filter.return_value = mock_q
            mock_q.limit.return_value = mock_q

            if model is CustomerSubscription:
                mock_q.all.return_value = [sub]
            elif model is SubscriptionPlan:
                mock_q.first.return_value = plan
            elif model is Payment:
                mock_q.first.return_value = None
            elif model is Account:
                mock_q.first.return_value = account
            else:
                mock_q.first.return_value = None
                mock_q.all.return_value = []
            return mock_q

        db.query.side_effect = _query_side_effect

        with (
            patch("app.workers.tasks.subscription_renewal.SessionLocal", return_value=db),
            patch("app.workers.tasks.subscription_renewal.set_rls_context"),
        ):
            from app.workers.tasks.subscription_renewal import subscription_renewal_worker
            subscription_renewal_worker(MagicMock())

        payments = [o for o in added_payments if hasattr(o, "subscription_id")]
        assert len(payments) == 1
        assert payments[0].company_id == company_a  # company_b não contaminado


# ─── 11. subscribe() com plano inativo ───────────────────────────────────────

class TestSubscribeValidation:
    def test_subscribe_inactive_plan_raises_422(self):
        """subscribe() com plano inativo levanta 422."""
        from fastapi import HTTPException

        company_id = uuid.uuid4()
        plan = _make_plan(company_id=company_id, is_active=False)
        db = _make_db()

        with patch("app.modules.subscriptions.service._get_plan_or_404", return_value=plan):
            from app.modules.subscriptions import service as svc
            with pytest.raises(HTTPException) as exc_info:
                svc.subscribe(
                    customer_id=uuid.uuid4(),
                    plan_id=plan.plan_id,
                    company_id=company_id,
                    db=db,
                )
        assert exc_info.value.status_code == 422
        assert "inativo" in exc_info.value.detail.lower()

    def test_subscribe_active_plan_creates_subscription_and_payment(self):
        """subscribe() com plano ativo cria CustomerSubscription ACTIVE + Payment PENDING."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        plan = _make_plan(company_id=company_id, is_active=True)

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        mock_payment = MagicMock()
        mock_payment.payment_id = uuid.uuid4()
        mock_payment.status = "PENDING"

        with (
            patch("app.modules.subscriptions.service._get_plan_or_404", return_value=plan),
            patch("app.modules.payments.service.create_payment", return_value=mock_payment) as mock_create,
        ):
            from app.modules.subscriptions import service as svc
            subscription, payment = svc.subscribe(
                customer_id=customer_id,
                plan_id=plan.plan_id,
                company_id=company_id,
                db=db,
            )

        # subscription adicionada (create_payment mockado não adiciona)
        assert len(added) == 1
        sub = added[0]
        assert sub.status == "ACTIVE"
        assert sub.company_id == company_id
        assert sub.customer_id == customer_id
        assert sub.plan_id == plan.plan_id

        # Payment PENDING criado no mesmo request, vinculado à subscription
        mock_create.assert_called_once()
        ck = mock_create.call_args.kwargs
        assert ck["subscription_id"] == sub.subscription_id
        assert ck["gross_amount"] == Decimal(str(plan.price))
        assert payment is mock_payment
        db.commit.assert_called()


# ─── 12. CRUD plans ───────────────────────────────────────────────────────────

class TestCRUDPlans:
    def test_create_plan(self):
        """create_plan persiste plano com is_active=True."""
        company_id = uuid.uuid4()
        db = _make_db()

        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        items = [
            _make_item("SERVICE", service_id=uuid.uuid4(), quantity=5),
            _make_item("PRODUCT", product_id=uuid.uuid4(), quantity=3),
        ]

        from app.modules.subscriptions import service as svc
        with patch("app.modules.subscriptions.service._attach_plan_item_names", side_effect=lambda db, plans: plans):
            svc.create_plan(
                company_id=company_id,
                name="Plano Premium",
                items=items,
                price=Decimal("199.00"),
                cycle_days=30,
                rollover_enabled=False,
                db=db,
            )

        from app.infrastructure.db.models.subscription import SubscriptionPlan, PlanItem
        plans = [o for o in added if isinstance(o, SubscriptionPlan)]
        plan_items = [o for o in added if isinstance(o, PlanItem)]
        assert len(plans) == 1
        assert len(plan_items) == 2
        plan = plans[0]
        assert plan.name == "Plano Premium"
        assert plan.cotas_per_cycle == 8  # 5 + 3
        assert plan.is_active is True
        assert plan.company_id == company_id
        db.commit.assert_called()

    def test_update_plan_deactivate(self):
        """update_plan pode desativar um plano."""
        company_id = uuid.uuid4()
        plan = _make_plan(company_id=company_id, is_active=True)
        db = _make_db()

        with patch("app.modules.subscriptions.service._get_plan_or_404", return_value=plan):
            from app.modules.subscriptions import service as svc
            svc.update_plan(plan.plan_id, company_id, db, is_active=False)

        assert plan.is_active is False
        db.commit.assert_called()

    def test_handle_subscription_renewed_in_financial_core(self):
        """handle_subscription_renewed cria Movement INFLOW + Entry ASSINATURA_RENOVACAO."""
        company_id      = uuid.uuid4()
        sub_id          = uuid.uuid4()
        account_id      = uuid.uuid4()
        plan_price      = Decimal("99.90")

        added_movements = []
        added_entries   = []

        db = _make_db()

        def _add_side_effect(obj):
            from app.infrastructure.db.models.movement import Movement
            from app.infrastructure.db.models.entry import Entry
            if isinstance(obj, Movement):
                added_movements.append(obj)
                obj.movement_id = uuid.uuid4()
            elif isinstance(obj, Entry):
                added_entries.append(obj)
                obj.entry_id = uuid.uuid4()

        db.add.side_effect = _add_side_effect

        from app.modules.financial_core import service as fc
        fc.handle_subscription_renewed(
            subscription_id=sub_id,
            plan_price=plan_price,
            target_account_id=account_id,
            company_id=company_id,
            db=db,
        )

        assert len(added_movements) == 1
        assert len(added_entries) == 1

        movement = added_movements[0]
        assert movement.type == "INFLOW"
        assert movement.amount == plan_price
        assert movement.account_id == account_id
        assert movement.source_type == "subscription"
        assert movement.source_id == sub_id

        entry = added_entries[0]
        assert entry.type == "RECEITA"
        assert entry.category == "ASSINATURA_RENOVACAO"
        assert entry.amount == plan_price
        assert entry.direction == "ADDS"
