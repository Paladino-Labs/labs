"""
Testes Sprint 26 — Pacotes e assinaturas multi-item.

Usa mocks (unittest.mock) — sem banco PostgreSQL real.

Casos:
  1.  Criar pacote com 2 itens (SERVICE + PRODUCT) → total_cotas = soma; 2 PackageItem
  2.  activate() → gera N créditos (1 por item) com service_id/product_id corretos
  3.  consume_for_operation com service_id correto → consome a cota do serviço certo
  4.  consume_for_operation com service_id sem cota → NoCreditAvailableError
  5.  Criar plano com 2 itens → cotas_per_cycle = soma; 2 PlanItem
  6.  Renovação de assinatura → gera N créditos (1 por item do plano)
  7.  subscribe() cria CustomerSubscription + Payment PENDING no mesmo request
  8.  find_available_credit retorna corretamente (has/none)
  9.  complete_appointment(use_credit=True) sem cota → 409
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


def _now():
    return datetime.now(timezone.utc)


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    db.close = MagicMock()
    return db


def _make_item(item_type="SERVICE", service_id=None, product_id=None, quantity=2):
    it = MagicMock()
    it.item_type = item_type
    it.service_id = service_id if item_type == "SERVICE" else None
    it.product_id = product_id if item_type == "PRODUCT" else None
    it.quantity = quantity
    return it


# ─── 1. Criar pacote com 2 itens ─────────────────────────────────────────────

class TestCreatePackageMultiItem:
    def test_create_package_two_items(self):
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        product_id = uuid.uuid4()
        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        items = [
            _make_item("SERVICE", service_id=service_id, quantity=3),
            _make_item("PRODUCT", product_id=product_id, quantity=2),
        ]

        from app.modules.packages import service as svc
        from app.infrastructure.db.models.package import Package, PackageItem

        with patch("app.modules.packages.service._attach_item_names", side_effect=lambda db, pkgs: pkgs):
            svc.create_package(
                company_id=company_id,
                name="Combo Barba + Pomada",
                items=items,
                price=Decimal("120.00"),
                validity_days=60,
                db=db,
            )

        packages = [o for o in added if isinstance(o, Package)]
        pkg_items = [o for o in added if isinstance(o, PackageItem)]
        assert len(packages) == 1
        assert packages[0].total_cotas == 5  # 3 + 2
        assert len(pkg_items) == 2
        types = {i.item_type for i in pkg_items}
        assert types == {"SERVICE", "PRODUCT"}
        # display_order sequencial
        assert sorted(i.display_order for i in pkg_items) == [0, 1]


# ─── 2. activate() → 1 crédito por item ──────────────────────────────────────

class TestActivatePerItem:
    def test_activate_creates_one_credit_per_item(self):
        company_id = uuid.uuid4()
        purchase_id = uuid.uuid4()
        service_id = uuid.uuid4()
        product_id = uuid.uuid4()

        pkg = MagicMock()
        pkg.validity_days = 30
        pkg.price = Decimal("120.00")
        pkg.items = [
            _make_item("SERVICE", service_id=service_id, quantity=3),
            _make_item("PRODUCT", product_id=product_id, quantity=2),
        ]

        purchase = MagicMock()
        purchase.purchase_id = purchase_id
        purchase.company_id = company_id
        purchase.customer_id = uuid.uuid4()
        purchase.seller_user_id = None
        purchase.status = "PENDING_PAYMENT"
        purchase.package = pkg

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        from app.modules.packages import service as svc
        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission"),
            patch("app.modules.packages.service._publish_purchased"),
        ):
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        credits = [o for o in added if hasattr(o, "entitlement_type")]
        assert len(credits) == 2

        by_service = {c.service_id: c for c in credits if c.service_id}
        by_product = {c.product_id: c for c in credits if c.product_id}
        assert service_id in by_service
        assert by_service[service_id].total_cotas == 3
        assert by_service[service_id].product_id is None
        assert product_id in by_product
        assert by_product[product_id].total_cotas == 2
        assert by_product[product_id].service_id is None
        for c in credits:
            assert c.entitlement_type == "PACKAGE"
            assert c.source_id == purchase_id
            assert c.status == "ACTIVE"


# ─── 3 & 4. consume_for_operation com match por service_id ───────────────────

class TestConsumeMatch:
    def _db_for_credit(self, credit):
        db = _make_db()

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
        return db

    def test_consume_with_correct_service_id(self):
        company_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        service_id = uuid.uuid4()

        credit = MagicMock()
        credit.credit_id = uuid.uuid4()
        credit.company_id = company_id
        credit.customer_id = customer_id
        credit.entitlement_type = "PACKAGE"
        credit.source_id = uuid.uuid4()
        credit.service_id = service_id
        credit.status = "ACTIVE"
        credit.remaining_cotas = 3
        credit.expires_at = None
        credit.granted_at = _now()

        db = self._db_for_credit(credit)

        from app.modules.customer_credit import service as svc
        svc.consume_for_operation(
            customer_id=customer_id,
            appointment_id=uuid.uuid4(),
            company_id=company_id,
            db=db,
            service_id=service_id,
        )
        assert credit.remaining_cotas == 2

    def test_consume_with_wrong_service_id_raises(self):
        """Sem cota para o service_id pedido (filtro exclui) → NoCreditAvailableError."""
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        db = self._db_for_credit(None)  # filtro por service_id errado → nada
        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=uuid.uuid4(),
                db=db,
                service_id=uuid.uuid4(),
            )

    def test_consume_filters_by_service_id(self):
        """Quando service_id é fornecido, o filtro CustomerCredit.service_id é aplicado."""
        from app.modules.customer_credit import service as svc
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        captured_filters = []

        db = _make_db()
        base_q = MagicMock()
        base_q.filter.side_effect = lambda *a, **k: (captured_filters.append(a), base_q)[1]
        base_q.order_by.return_value = base_q
        base_q.with_for_update.return_value = base_q
        base_q.first.return_value = None
        db.query.return_value = base_q

        with pytest.raises(NoCreditAvailableError):
            svc.consume_for_operation(
                customer_id=uuid.uuid4(),
                appointment_id=None,
                company_id=company_id,
                db=db,
                service_id=service_id,
            )
        # Houve ao menos 2 chamadas de filter (base + match por service_id)
        assert len(captured_filters) >= 2


# ─── 5. Criar plano com 2 itens ──────────────────────────────────────────────

class TestCreatePlanMultiItem:
    def test_create_plan_two_items(self):
        company_id = uuid.uuid4()
        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        items = [
            _make_item("SERVICE", service_id=uuid.uuid4(), quantity=4),
            _make_item("PRODUCT", product_id=uuid.uuid4(), quantity=1),
        ]

        from app.modules.subscriptions import service as svc
        from app.infrastructure.db.models.subscription import SubscriptionPlan, PlanItem

        with patch("app.modules.subscriptions.service._attach_plan_item_names", side_effect=lambda db, plans: plans):
            svc.create_plan(
                company_id=company_id,
                name="Plano Combo",
                items=items,
                price=Decimal("150.00"),
                cycle_days=30,
                db=db,
            )

        plans = [o for o in added if isinstance(o, SubscriptionPlan)]
        plan_items = [o for o in added if isinstance(o, PlanItem)]
        assert len(plans) == 1
        assert plans[0].cotas_per_cycle == 5  # 4 + 1
        assert len(plan_items) == 2


# ─── 6. Renovação → 1 crédito por item do plano ──────────────────────────────

class TestSubscriptionRenewalPerItem:
    def test_renewal_creates_credit_per_item(self):
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        sub_id = uuid.uuid4()
        service_id = uuid.uuid4()
        product_id = uuid.uuid4()

        plan = MagicMock()
        plan.plan_id = uuid.uuid4()
        plan.price = Decimal("150.00")
        plan.cycle_days = 30
        plan.rollover_enabled = False
        plan.items = [
            _make_item("SERVICE", service_id=service_id, quantity=4),
            _make_item("PRODUCT", product_id=product_id, quantity=1),
        ]

        sub = MagicMock()
        sub.subscription_id = sub_id
        sub.company_id = company_id
        sub.customer_id = uuid.uuid4()
        sub.plan_id = plan.plan_id
        sub.status = "ACTIVE"

        payment = MagicMock()
        payment.payment_id = payment_id
        payment.company_id = company_id
        payment.subscription_id = sub_id
        payment.target_account_id = uuid.uuid4()

        event = MagicMock()
        event.payload = {"payment_id": str(payment_id)}
        event.company_id = company_id
        event.event_id = uuid.uuid4()

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

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

        credits = [o for o in added if hasattr(o, "entitlement_type")]
        assert len(credits) == 2
        by_service = {c.service_id: c for c in credits if c.service_id}
        by_product = {c.product_id: c for c in credits if c.product_id}
        assert by_service[service_id].total_cotas == 4
        assert by_product[product_id].total_cotas == 1
        for c in credits:
            assert c.entitlement_type == "SUBSCRIPTION"
            assert c.source_id == sub_id


# ─── 7. subscribe() cria Payment PENDING ─────────────────────────────────────

class TestSubscribeCreatesPayment:
    def test_subscribe_creates_subscription_and_payment(self):
        company_id = uuid.uuid4()
        customer_id = uuid.uuid4()

        plan = MagicMock()
        plan.plan_id = uuid.uuid4()
        plan.is_active = True
        plan.price = Decimal("150.00")
        plan.cycle_days = 30

        db = _make_db()
        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        mock_payment = MagicMock()
        mock_payment.payment_id = uuid.uuid4()

        from app.modules.subscriptions import service as svc
        with (
            patch("app.modules.subscriptions.service._get_plan_or_404", return_value=plan),
            patch("app.modules.payments.service.create_payment", return_value=mock_payment) as mock_create,
        ):
            subscription, payment = svc.subscribe(
                customer_id=customer_id,
                plan_id=plan.plan_id,
                company_id=company_id,
                db=db,
                payment_method="PIX",
            )

        subs = [o for o in added if hasattr(o, "status") and getattr(o, "status", None) == "ACTIVE"]
        assert len(subs) == 1
        mock_create.assert_called_once()
        ck = mock_create.call_args.kwargs
        assert ck["subscription_id"] == subscription.subscription_id
        assert ck["payment_method"] == "PIX"
        assert payment is mock_payment


# ─── 8. find_available_credit ────────────────────────────────────────────────

class TestFindAvailableCredit:
    def test_returns_credit_when_available(self):
        company_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        service_id = uuid.uuid4()

        credit = MagicMock()
        credit.credit_id = uuid.uuid4()
        credit.remaining_cotas = 4
        credit.service_id = service_id

        db = _make_db()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = credit
        db.query.return_value = q

        from app.modules.customer_credit import service as svc
        result = svc.find_available_credit(
            customer_id=customer_id, company_id=company_id, db=db, service_id=service_id
        )
        assert result is credit

    def test_returns_none_when_no_credit(self):
        db = _make_db()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = None
        db.query.return_value = q

        from app.modules.customer_credit import service as svc
        result = svc.find_available_credit(
            customer_id=uuid.uuid4(), company_id=uuid.uuid4(), db=db, service_id=uuid.uuid4()
        )
        assert result is None


# ─── 9. complete_appointment(use_credit=True) sem cota → 409 ─────────────────

class TestCompleteWithCredit:
    def _make_appointment(self, company_id, service_id):
        appt = MagicMock()
        appt.id = uuid.uuid4()
        appt.company_id = company_id
        appt.client_id = uuid.uuid4()
        svc_line = MagicMock()
        svc_line.service_id = service_id
        appt.services = [svc_line]
        return appt

    def test_complete_use_credit_no_cota_raises_409(self):
        from fastapi import HTTPException
        from app.modules.customer_credit.exceptions import NoCreditAvailableError

        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        appt = self._make_appointment(company_id, service_id)
        db = _make_db()

        from app.modules.appointments import service as asvc
        with (
            patch("app.modules.appointments.service.get_appointment_or_404", return_value=appt),
            patch(
                "app.modules.customer_credit.service.consume_for_operation",
                side_effect=NoCreditAvailableError(),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                asvc.complete_appointment(
                    db, company_id, appt.id, uuid.uuid4(), use_credit=True
                )
        assert exc_info.value.status_code == 409
        db.rollback.assert_called()

    def test_complete_use_credit_success_consumes_and_completes(self):
        company_id = uuid.uuid4()
        service_id = uuid.uuid4()
        appt = self._make_appointment(company_id, service_id)
        db = _make_db()

        from app.modules.appointments import service as asvc
        with (
            patch("app.modules.appointments.service.get_appointment_or_404", return_value=appt),
            patch("app.modules.customer_credit.service.consume_for_operation") as mock_consume,
            patch("app.modules.appointments.service.transition") as mock_transition,
            patch("app.modules.appointments.service._recognize_deposit_balance"),
        ):
            asvc.complete_appointment(
                db, company_id, appt.id, uuid.uuid4(), use_credit=True
            )

        mock_consume.assert_called_once()
        ck = mock_consume.call_args.kwargs
        assert ck["service_id"] == service_id
        assert ck["customer_id"] == appt.client_id
        mock_transition.assert_called_once()
        db.commit.assert_called()
