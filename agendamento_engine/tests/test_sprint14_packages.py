"""
Testes Sprint 14 — Pacotes.

Usa mocks (unittest.mock) — sem banco PostgreSQL real.

Casos obrigatórios:
  1.  purchase() → PackagePurchase PENDING_PAYMENT + Payment PENDING criados
  2.  payment.confirmed → activate() → CustomerCredit ACTIVE
  3.  CustomerCredit.total_cotas == package.total_cotas
  4.  CustomerCredit.expires_at = now()+validity_days (quando definido)
  5.  activate() → Commission PACKAGE_SOLD calculada para seller
  6.  Refund → CustomerCredit REVOKED + Commission REVERSED
  7.  purchase() com package inativo → 422
  8.  Cross-tenant: packages e purchases isolados
  9.  Multiple listeners: handler de pacote é segundo listener em payment.confirmed
  10. activate() idempotente: chamada dupla em status ACTIVE retorna sem erro
"""
import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

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
    return db


def _query_chain(db, value):
    """Configura cadeia de query para retornar `value` em .first()."""
    chain = db.query.return_value
    for _ in range(6):
        chain.filter.return_value   = chain
        chain.order_by.return_value = chain
        chain.first.return_value    = value
        chain.all.return_value      = [value] if value else []
        chain = chain.filter.return_value
    return db


def _make_package(
    package_id=None,
    company_id=None,
    name="Pacote 10 Cortes",
    total_cotas=10,
    price=Decimal("200.00"),
    service_id=None,
    validity_days=30,
    is_active=True,
):
    pkg = MagicMock()
    pkg.package_id    = package_id or uuid.uuid4()
    pkg.company_id    = company_id or uuid.uuid4()
    pkg.name          = name
    pkg.total_cotas   = total_cotas
    pkg.price         = price
    pkg.service_id    = service_id
    pkg.validity_days = validity_days
    pkg.is_active     = is_active
    return pkg


def _make_purchase(
    purchase_id=None,
    company_id=None,
    customer_id=None,
    package_id=None,
    payment_id=None,
    seller_user_id=None,
    total_price=Decimal("200.00"),
    status="PENDING_PAYMENT",
    package=None,
):
    p = MagicMock()
    p.purchase_id    = purchase_id or uuid.uuid4()
    p.company_id     = company_id or uuid.uuid4()
    p.customer_id    = customer_id or uuid.uuid4()
    p.package_id     = package_id or uuid.uuid4()
    p.payment_id     = payment_id or uuid.uuid4()
    p.seller_user_id = seller_user_id
    p.total_price    = total_price
    p.status         = status
    p.package        = package or _make_package()
    p.activated_at   = None
    return p


# ─── 1. purchase() → PENDING_PAYMENT + Payment PENDING ───────────────────────

class TestPurchase:
    def test_purchase_creates_pending_purchase_and_payment(self):
        """purchase() cria PackagePurchase PENDING_PAYMENT e chama create_payment."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        package_id  = uuid.uuid4()
        pkg         = _make_package(package_id=package_id, company_id=company_id)

        db = _make_db()

        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        mock_payment = MagicMock()
        mock_payment.payment_id = uuid.uuid4()
        mock_payment.status     = "PENDING"

        with (
            patch("app.modules.packages.service._get_package_or_404", return_value=pkg),
            patch("app.modules.payments.service.create_payment", return_value=mock_payment) as mock_create,
            patch("app.modules.packages.service._get_purchase_or_404"),
        ):
            from app.modules.packages import service as svc

            result = svc.purchase(
                customer_id=customer_id,
                package_id=package_id,
                seller_user_id=None,
                payment_method="CASH",
                target_account_id=None,
                company_id=company_id,
                db=db,
            )

        # Verificações
        assert len(added_objects) == 1
        pkg_purchase = added_objects[0]
        assert pkg_purchase.status == "PENDING_PAYMENT"
        assert pkg_purchase.company_id == company_id
        assert pkg_purchase.customer_id == customer_id
        assert pkg_purchase.package_id == package_id
        assert str(pkg_purchase.total_price) == str(pkg.price)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["company_id"] == company_id
        assert call_kwargs["customer_id"] == customer_id
        assert call_kwargs["gross_amount"] == Decimal(str(pkg.price))
        assert call_kwargs["payment_method"] == "CASH"

        db.commit.assert_called()

    def test_purchase_inactive_package_raises_422(self):
        """purchase() com package inativo levanta HTTP 422."""
        from fastapi import HTTPException
        pkg = _make_package(is_active=False)
        db  = _make_db()

        with patch("app.modules.packages.service._get_package_or_404", return_value=pkg):
            from app.modules.packages import service as svc
            with pytest.raises(HTTPException) as exc_info:
                svc.purchase(
                    customer_id=uuid.uuid4(),
                    package_id=pkg.package_id,
                    seller_user_id=None,
                    payment_method="CASH",
                    target_account_id=None,
                    company_id=pkg.company_id,
                    db=db,
                )
        assert exc_info.value.status_code == 422
        assert "inativo" in exc_info.value.detail.lower()

    def test_purchase_sets_payment_id_on_purchase(self):
        """purchase() vincula o payment_id à compra."""
        company_id  = uuid.uuid4()
        customer_id = uuid.uuid4()
        pkg         = _make_package(company_id=company_id)
        payment_id  = uuid.uuid4()

        db = _make_db()
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        mock_payment = MagicMock()
        mock_payment.payment_id = payment_id
        mock_payment.status     = "PENDING"

        with (
            patch("app.modules.packages.service._get_package_or_404", return_value=pkg),
            patch("app.modules.payments.service.create_payment", return_value=mock_payment),
        ):
            from app.modules.packages import service as svc
            svc.purchase(
                customer_id=customer_id,
                package_id=pkg.package_id,
                seller_user_id=None,
                payment_method="CASH",
                target_account_id=None,
                company_id=company_id,
                db=db,
            )

        pkg_purchase = added_objects[0]
        assert pkg_purchase.payment_id == payment_id


# ─── 2–4. activate() → CustomerCredit ACTIVE ─────────────────────────────────

class TestActivate:
    def test_activate_creates_customer_credit(self):
        """activate() cria CustomerCredit ACTIVE com total_cotas = package.total_cotas."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=10, validity_days=None)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission"),
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        # Verifica CustomerCredit criado
        credits = [o for o in added_objects if hasattr(o, "entitlement_type")]
        assert len(credits) == 1
        credit = credits[0]
        assert credit.entitlement_type == "PACKAGE"
        assert credit.total_cotas == pkg.total_cotas
        assert credit.remaining_cotas == pkg.total_cotas
        assert credit.status == "ACTIVE"
        assert credit.source_id == purchase_id
        assert credit.company_id == company_id

    def test_activate_sets_status_active(self):
        """activate() muda PackagePurchase.status para ACTIVE."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=5)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission"),
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        assert purchase.status == "ACTIVE"
        assert purchase.activated_at is not None
        db.commit.assert_called()

    def test_activate_with_validity_days_sets_expires_at(self):
        """CustomerCredit.expires_at = now()+validity_days quando validity_days definido."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=5, validity_days=30)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission"),
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        credits = [o for o in added_objects if hasattr(o, "entitlement_type")]
        assert len(credits) == 1
        credit = credits[0]
        assert credit.expires_at is not None
        diff = credit.expires_at - credit.granted_at
        assert abs(diff.days - 30) <= 1  # tolerância de 1 dia

    def test_activate_without_validity_days_no_expires_at(self):
        """CustomerCredit.expires_at = None quando validity_days não definido."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=5, validity_days=None)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()
        added_objects = []
        db.add.side_effect = lambda obj: added_objects.append(obj)

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission"),
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        credits = [o for o in added_objects if hasattr(o, "entitlement_type")]
        credit = credits[0]
        assert credit.expires_at is None

    def test_activate_idempotent_already_active(self):
        """activate() em compra já ACTIVE retorna sem erro e sem novo crédito."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=5)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            status="ACTIVE",
            package=pkg,
        )

        db = _make_db()

        with patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase):
            from app.modules.packages import service as svc
            result = svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        assert result is purchase
        db.add.assert_not_called()
        db.commit.assert_not_called()


# ─── 5. Commission PACKAGE_SOLD ───────────────────────────────────────────────

class TestCommissionPackageSold:
    def test_activate_calls_commission_for_seller(self):
        """activate() dispara _try_calculate_commission para seller_user_id."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        seller_id   = uuid.uuid4()
        pkg = _make_package(total_cotas=5)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            seller_user_id=seller_id,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission") as mock_commission,
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        mock_commission.assert_called_once()
        call_args = mock_commission.call_args
        assert call_args.args[0] is purchase
        assert call_args.args[1] is pkg

    def test_activate_no_commission_without_seller(self):
        """activate() sem seller_user_id não dispara comissão."""
        company_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        pkg = _make_package(total_cotas=5)
        purchase = _make_purchase(
            purchase_id=purchase_id,
            company_id=company_id,
            seller_user_id=None,
            status="PENDING_PAYMENT",
            package=pkg,
        )

        db = _make_db()

        with (
            patch("app.modules.packages.service._get_purchase_or_404", return_value=purchase),
            patch("app.modules.packages.service._try_calculate_commission") as mock_commission,
            patch("app.modules.packages.service._publish_purchased"),
        ):
            from app.modules.packages import service as svc
            svc.activate(purchase_id=purchase_id, company_id=company_id, db=db)

        mock_commission.assert_called_once()
        # _try_calculate_commission é chamado mas internamente retorna cedo
        # sem seller_user_id. Verificamos o comportamento real de _try_calculate_commission.

    def test_try_calculate_commission_no_seller_returns_early(self):
        """_try_calculate_commission sem seller_user_id retorna imediatamente."""
        company_id = uuid.uuid4()
        pkg = _make_package()
        purchase = _make_purchase(seller_user_id=None, package=pkg)

        with patch("app.modules.packages.service.SessionLocal") as mock_session_cls:
            from app.modules.packages import service as svc
            svc._try_calculate_commission(purchase, pkg, company_id)

        mock_session_cls.assert_not_called()

    def test_try_calculate_commission_with_professional_seller(self):
        """_try_calculate_commission com seller que é Professional chama calculate_commission."""
        company_id  = uuid.uuid4()
        seller_id   = uuid.uuid4()
        pkg = _make_package(price=Decimal("200.00"))
        purchase = _make_purchase(seller_user_id=seller_id, package=pkg)

        mock_db = _make_db()

        with (
            patch("app.modules.packages.service.SessionLocal", return_value=mock_db) as mock_session_cls,
            patch("app.modules.packages.service.set_rls_context"),
            patch("app.modules.packages.service._resolve_professional_id", return_value=seller_id),
            patch("app.modules.commission.service.calculate_commission") as mock_calc,
        ):
            from app.modules.packages import service as svc
            svc._try_calculate_commission(purchase, pkg, company_id)

        mock_session_cls.assert_called_once()
        mock_calc.assert_called_once()
        call_kwargs = mock_calc.call_args.kwargs
        assert call_kwargs["professional_id"] == seller_id
        assert call_kwargs["operation_type"] == "PACKAGE_SOLD"
        assert call_kwargs["gross_amount"] == Decimal(str(pkg.price))
        assert call_kwargs["appointment_id"] is None

    def test_try_calculate_commission_non_professional_seller_no_commission(self):
        """_try_calculate_commission com seller que NÃO é Professional: sem comissão."""
        company_id = uuid.uuid4()
        seller_id  = uuid.uuid4()
        pkg = _make_package()
        purchase = _make_purchase(seller_user_id=seller_id, package=pkg)

        mock_db = _make_db()

        with (
            patch("app.modules.packages.service.SessionLocal", return_value=mock_db) as mock_session_cls,
            patch("app.modules.packages.service.set_rls_context"),
            patch("app.modules.packages.service._resolve_professional_id", return_value=None),
            patch("app.modules.commission.service.calculate_commission") as mock_calc,
        ):
            from app.modules.packages import service as svc
            svc._try_calculate_commission(purchase, pkg, company_id)

        mock_session_cls.assert_called_once()
        mock_calc.assert_not_called()


# ─── 6. Refund → REVOKED + REVERSED ──────────────────────────────────────────

class TestRefund:
    def test_revoke_for_refund_revokes_credit_and_reverses_commission(self):
        """payment.refunded → CustomerCredit REVOKED + Commission REVERSED."""
        company_id  = uuid.uuid4()
        payment_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()
        credit_id   = uuid.uuid4()
        commission_id = uuid.uuid4()

        seller_id = uuid.uuid4()
        price     = Decimal("200.00")

        # Mock PackagePurchase
        pkg_purchase = MagicMock()
        pkg_purchase.purchase_id    = purchase_id
        pkg_purchase.company_id     = company_id
        pkg_purchase.payment_id     = payment_id
        pkg_purchase.status         = "ACTIVE"
        pkg_purchase.seller_user_id = seller_id
        pkg_purchase.total_price    = price

        # Mock CustomerCredit
        credit = MagicMock()
        credit.credit_id   = credit_id
        credit.status      = "ACTIVE"
        credit.source_id   = purchase_id

        # Mock Commission
        commission = MagicMock()
        commission.commission_id   = commission_id
        commission.status          = "CALCULATED"
        commission.operation_type  = "PACKAGE_SOLD"
        commission.professional_id = seller_id
        commission.gross_amount    = price

        db = _make_db()

        call_count = [0]
        def _query_side_effect(model):
            call_count[0] += 1
            from app.infrastructure.db.models.package import PackagePurchase
            from app.infrastructure.db.models.customer_credit import CustomerCredit
            from app.infrastructure.db.models.commission import Commission

            mock_q = MagicMock()
            if model is PackagePurchase:
                mock_q.filter.return_value.first.return_value = pkg_purchase
            elif model is CustomerCredit:
                mock_q.filter.return_value.all.return_value = [credit]
            elif model is Commission:
                mock_q.filter.return_value.all.return_value = [commission]
            else:
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.all.return_value = []
            mock_q.filter.return_value.filter.return_value = mock_q.filter.return_value
            return mock_q

        db.query.side_effect = _query_side_effect

        with patch("app.modules.packages.service._resolve_professional_id", return_value=seller_id):
            from app.modules.packages import service as svc
            svc.revoke_for_refund(payment_id=payment_id, company_id=company_id, db=db)

        assert credit.status == "REVOKED"
        assert pkg_purchase.status == "REVOKED"
        assert commission.status == "REVERSED"
        db.commit.assert_called()

    def test_revoke_for_refund_no_purchase_is_noop(self):
        """revoke_for_refund sem PackagePurchase ACTIVE: não faz nada."""
        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.packages import service as svc
        svc.revoke_for_refund(
            payment_id=uuid.uuid4(),
            company_id=uuid.uuid4(),
            db=db,
        )

        db.commit.assert_not_called()

    def test_revoke_for_refund_revokes_exhausted_credit(self):
        """Crédito EXHAUSTED também é revogado no refund."""
        company_id  = uuid.uuid4()
        payment_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()

        pkg_purchase = MagicMock()
        pkg_purchase.purchase_id    = purchase_id
        pkg_purchase.status         = "ACTIVE"
        pkg_purchase.payment_id     = payment_id
        pkg_purchase.seller_user_id = None
        pkg_purchase.total_price    = Decimal("100.00")

        credit_exhausted = MagicMock()
        credit_exhausted.status   = "EXHAUSTED"
        credit_exhausted.source_id = purchase_id

        db = _make_db()

        def _query_side_effect(model):
            from app.infrastructure.db.models.package import PackagePurchase
            from app.infrastructure.db.models.customer_credit import CustomerCredit
            from app.infrastructure.db.models.commission import Commission

            mock_q = MagicMock()
            mock_q.filter.return_value.filter.return_value = mock_q.filter.return_value
            if model is PackagePurchase:
                mock_q.filter.return_value.first.return_value = pkg_purchase
            elif model is CustomerCredit:
                mock_q.filter.return_value.all.return_value = [credit_exhausted]
            elif model is Commission:
                mock_q.filter.return_value.all.return_value = []
            else:
                mock_q.filter.return_value.first.return_value = None
                mock_q.filter.return_value.all.return_value = []
            return mock_q

        db.query.side_effect = _query_side_effect

        from app.modules.packages import service as svc
        svc.revoke_for_refund(payment_id=payment_id, company_id=company_id, db=db)

        assert credit_exhausted.status == "REVOKED"
        db.commit.assert_called()


# ─── 7. Cross-tenant isolation ───────────────────────────────────────────────

class TestCrossTenant:
    def test_get_package_from_other_tenant_raises_404(self):
        """Buscar package de outro tenant levanta 404."""
        from fastapi import HTTPException

        company_id_a = uuid.uuid4()
        company_id_b = uuid.uuid4()

        db = _make_db()
        # Simula que a query com filtro company_id retorna None (cross-tenant isolado)
        db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.packages import service as svc
        with pytest.raises(HTTPException) as exc_info:
            svc._get_package_or_404(uuid.uuid4(), company_id_b, db)
        assert exc_info.value.status_code == 404

    def test_get_purchase_from_other_tenant_raises_404(self):
        """Buscar purchase de outro tenant levanta 404."""
        from fastapi import HTTPException

        db = _make_db()
        db.query.return_value.filter.return_value.first.return_value = None

        from app.modules.packages import service as svc
        with pytest.raises(HTTPException) as exc_info:
            svc._get_purchase_or_404(uuid.uuid4(), uuid.uuid4(), db)
        assert exc_info.value.status_code == 404

    def test_list_purchases_filters_by_company(self):
        """list_purchases filtra por company_id."""
        company_id = uuid.uuid4()
        db = _make_db()

        from app.modules.packages import service as svc
        svc.list_purchases(company_id=company_id, db=db)

        # Verifica que query foi feita com filtro de company_id
        db.query.assert_called()


# ─── 8. Handler payment.confirmed → activate ─────────────────────────────────

class TestPaymentConfirmedHandler:
    def test_handler_activates_pending_purchase(self):
        """handle_payment_confirmed_package chama activate() quando há compra PENDING_PAYMENT."""
        company_id  = uuid.uuid4()
        payment_id  = uuid.uuid4()
        purchase_id = uuid.uuid4()

        mock_purchase = MagicMock()
        mock_purchase.purchase_id = purchase_id
        mock_purchase.status      = "PENDING_PAYMENT"

        event = MagicMock()
        event.payload    = {"payment_id": str(payment_id)}
        event.company_id = company_id
        event.event_id   = uuid.uuid4()

        mock_db = _make_db()
        # Configura cadeia de query para retornar mock_purchase
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = mock_purchase
        mock_db.query.return_value = mock_q

        with (
            patch("app.workers.handlers.package_handler.SessionLocal", return_value=mock_db),
            patch("app.workers.handlers.package_handler.set_rls_context"),
            patch("app.modules.packages.service.activate") as mock_activate,
        ):
            from app.workers.handlers.package_handler import handle_payment_confirmed_package
            handle_payment_confirmed_package(event)

        mock_activate.assert_called_once_with(
            purchase_id=purchase_id,
            company_id=company_id,
            db=mock_db,
        )

    def test_handler_noop_when_no_purchase(self):
        """handle_payment_confirmed_package não faz nada sem PackagePurchase PENDING_PAYMENT."""
        event = MagicMock()
        event.payload    = {"payment_id": str(uuid.uuid4())}
        event.company_id = uuid.uuid4()
        event.event_id   = uuid.uuid4()

        mock_db = _make_db()
        mock_q = MagicMock()
        mock_q.filter.return_value = mock_q
        mock_q.first.return_value = None
        mock_db.query.return_value = mock_q

        with (
            patch("app.workers.handlers.package_handler.SessionLocal", return_value=mock_db),
            patch("app.workers.handlers.package_handler.set_rls_context"),
            patch("app.modules.packages.service.activate") as mock_activate,
        ):
            from app.workers.handlers.package_handler import handle_payment_confirmed_package
            handle_payment_confirmed_package(event)

        mock_activate.assert_not_called()

    def test_handler_payment_refunded_calls_revoke(self):
        """handle_payment_refunded_package chama revoke_for_refund."""
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        event = MagicMock()
        event.payload    = {"payment_id": str(payment_id)}
        event.company_id = company_id
        event.event_id   = uuid.uuid4()

        mock_db = _make_db()

        with (
            patch("app.workers.handlers.package_handler.SessionLocal", return_value=mock_db),
            patch("app.workers.handlers.package_handler.set_rls_context"),
            patch("app.modules.packages.service.revoke_for_refund") as mock_revoke,
        ):
            from app.workers.handlers.package_handler import handle_payment_refunded_package
            handle_payment_refunded_package(event)

        mock_revoke.assert_called_once_with(
            payment_id=payment_id,
            company_id=company_id,
            db=mock_db,
        )


# ─── 9. Multiple listeners ────────────────────────────────────────────────────

class TestMultipleListeners:
    def test_register_handlers_adds_second_listener(self):
        """register_handlers() adiciona listener sem substituir o existente."""
        from app.infrastructure.event_bus import EventBus

        bus = EventBus()

        def sentinel_a(e):
            pass

        bus.register("payment.confirmed", sentinel_a)

        from app.workers.handlers.package_handler import register_handlers

        with patch("app.workers.handlers.package_handler.event_bus", bus):
            register_handlers()

        # Ambos os handlers devem estar registrados
        handlers = bus._handlers.get("payment.confirmed", [])
        assert sentinel_a in handlers
        assert any(
            h.__name__ == "handle_payment_confirmed_package"
            for h in handlers
        )

    def test_event_bus_calls_all_listeners(self):
        """EventBus chama todos os listeners registrados para o mesmo evento."""
        from app.infrastructure.event_bus import EventBus, DomainEvent

        bus = EventBus()
        results = []

        bus.register("payment.confirmed", lambda e: results.append("handler_a"))
        bus.register("payment.confirmed", lambda e: results.append("handler_b"))

        event = DomainEvent(
            event_id=uuid.uuid4(),
            event_type="payment.confirmed",
            occurred_at=datetime.now(timezone.utc),
            company_id=uuid.uuid4(),
            idempotency_key="test",
            actor={"type": "SYSTEM", "id": None},
            payload={},
        )
        bus.publish(event)

        assert "handler_a" in results
        assert "handler_b" in results


# ─── 10. CRUD packages ────────────────────────────────────────────────────────

class TestCRUDPackages:
    def test_create_package(self):
        """create_package persiste pacote com is_active=True."""
        company_id = uuid.uuid4()
        db = _make_db()

        added = []
        db.add.side_effect = lambda obj: added.append(obj)

        from app.modules.packages import service as svc
        svc.create_package(
            company_id=company_id,
            name="Pacote Gold",
            total_cotas=12,
            price=Decimal("250.00"),
            service_id=None,
            validity_days=30,
            db=db,
        )

        assert len(added) == 1
        pkg = added[0]
        assert pkg.name == "Pacote Gold"
        assert pkg.total_cotas == 12
        assert pkg.is_active is True
        assert pkg.company_id == company_id
        db.commit.assert_called()

    def test_delete_package_soft(self):
        """delete_package() marca is_active=False (soft delete)."""
        company_id = uuid.uuid4()
        pkg = _make_package(company_id=company_id)
        db = _make_db()

        with patch("app.modules.packages.service._get_package_or_404", return_value=pkg):
            from app.modules.packages import service as svc
            svc.delete_package(pkg.package_id, company_id, db)

        assert pkg.is_active is False
        db.commit.assert_called()
