"""
Testes Sprint 16 — Promoções e Cupons (PromotionEngine + CouponService).

Usa mocks (unittest.mock) — sem banco PostgreSQL real (padrão do projeto),
exceto o teste de race de uses_count (skipif sem DATABASE_URL).

Casos obrigatórios:
  1.  compute_preview: zero persistência (nenhum add/flush/commit)
  2.  Promoções exclusivas → seleciona maior desconto (CUSTOMER_FAVORABLE)
  3.  Cumulativas aplicadas em sequência sobre residual
  4.  Cupom esgotado (uses_count >= max_uses) → 422
  5.  Cupom PER_CUSTOMER usado por outro cliente → 422
  6.  Revalidação: promoção pausada entre preview e confirm →
      promotion.effectuation_failed (não bloqueia pagamento)
  7.  Race de uses_count: SINGLE_USE concorrente → apenas um redeem
      (PostgreSQL real — skip em SQLite/mocks)
  8.  Refund → CouponRedemption.reverted_at preenchido (+ reopen policy)
  9.  manual-discount sem reason → 422
  10. manual-discount OPERATOR → 403
  11. Cross-tenant: promoção de empresa A invisível para B
  12. DRE: desconto reduz receita (Entry RECEITA = net com desconto)
"""
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.modules.promotions import service as promotion_service
from app.modules.payments import service as payment_service

DATABASE_URL = os.getenv("DATABASE_URL", "")


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _make_promotion(
    promotion_id=None,
    company_id=None,
    name="Promo Teste",
    discount_type="PERCENTAGE",
    discount_value=Decimal("10"),
    application_mode="AUTOMATIC",
    cumulative=False,
    priority=0,
    status="ACTIVE",
    valid_from=None,
    valid_until=None,
    max_uses=None,
    max_uses_per_customer=None,
    uses_count=0,
    conditions=None,
):
    p = MagicMock()
    p.id = promotion_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.name = name
    p.discount_type = discount_type
    p.discount_value = discount_value
    p.application_mode = application_mode
    p.cumulative = cumulative
    p.priority = priority
    p.status = status
    p.valid_from = valid_from
    p.valid_until = valid_until
    p.max_uses = max_uses
    p.max_uses_per_customer = max_uses_per_customer
    p.uses_count = uses_count
    p.conditions = conditions
    return p


def _make_coupon(
    coupon_id=None,
    company_id=None,
    promotion_id=None,
    code="CUPOM10",
    generation_type="SINGLE_USE",
    max_uses=1,
    uses_count=0,
    coupon_reopen_policy="NEVER_REOPEN",
    status="ACTIVE",
    customer_id=None,
    expires_at=None,
):
    c = MagicMock()
    c.id = coupon_id or uuid.uuid4()
    c.company_id = company_id or uuid.uuid4()
    c.promotion_id = promotion_id or uuid.uuid4()
    c.code = code
    c.generation_type = generation_type
    c.max_uses = max_uses
    c.uses_count = uses_count
    c.coupon_reopen_policy = coupon_reopen_policy
    c.status = status
    c.customer_id = customer_id
    c.expires_at = expires_at
    return c


def _make_db(
    promotions=None,
    promotion_single=None,
    coupon=None,
    redemptions_count=0,
    redemptions=None,
    existing_application=None,
    applications=None,
    application_count=0,
    payment=None,
):
    """Mock de Session com dispatch por nome do modelo."""
    db = MagicMock()

    def _query(model_class):
        q = MagicMock()
        name = getattr(model_class, "__name__", str(model_class))
        if name == "Promotion":
            q.filter.return_value.all.return_value = promotions or []
            q.filter.return_value.first.return_value = promotion_single
        elif name == "Coupon":
            chain = q.filter.return_value
            chain.first.return_value = coupon
            chain.with_for_update.return_value.first.return_value = coupon
        elif name == "CouponRedemption":
            q.filter.return_value.count.return_value = redemptions_count
            q.filter.return_value.all.return_value = redemptions or []
        elif name == "DiscountApplication":
            q.filter.return_value.first.return_value = existing_application
            q.filter.return_value.count.return_value = application_count
            q.filter.return_value.all.return_value = applications or []
        elif name == "Payment":
            q.filter.return_value.first.return_value = payment
        else:
            q.filter.return_value.first.return_value = None
            q.filter.return_value.all.return_value = []
        return q

    db.query.side_effect = _query
    return db


def _make_payment(
    company_id=None,
    status="PENDING",
    gross=Decimal("100.00"),
    discount=Decimal("0"),
    coupon_code=None,
):
    p = MagicMock()
    p.payment_id = uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.customer_id = uuid.uuid4()
    p.status = status
    p.gross_catalog_amount = gross
    p.discount_amount = discount
    p.net_charged_amount = gross - discount
    p.manual_override_count = 0
    p.coupon_code = coupon_code
    return p


# ─── 1. compute_preview: zero persistência ────────────────────────────────────

class TestPreviewZeroSideEffects:
    def test_preview_does_not_persist_anything(self):
        company_id = uuid.uuid4()
        promo = _make_promotion(company_id=company_id, discount_value=Decimal("10"))
        db = _make_db(promotions=[promo])

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
        )

        db.add.assert_not_called()
        db.flush.assert_not_called()
        db.commit.assert_not_called()
        assert Decimal(result["discount_total"]) == Decimal("10.00")
        assert Decimal(result["final_amount"]) == Decimal("90.00")

    def test_preview_with_coupon_does_not_persist(self):
        company_id = uuid.uuid4()
        promo = _make_promotion(
            company_id=company_id, application_mode="COUPON_REQUIRED",
            discount_type="FIXED_AMOUNT", discount_value=Decimal("15"),
        )
        coupon = _make_coupon(company_id=company_id, promotion_id=promo.id)
        db = _make_db(promotions=[promo], coupon=coupon)

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
            coupon_code="CUPOM10",
        )

        db.add.assert_not_called()
        db.commit.assert_not_called()
        assert result["coupon_valid"] is True
        assert Decimal(result["discount_total"]) == Decimal("15")
        assert coupon.uses_count == 0  # preview não incrementa


# ─── 2. Exclusivas → maior desconto (CUSTOMER_FAVORABLE) ─────────────────────

class TestExclusivePromotions:
    def test_largest_discount_wins(self):
        company_id = uuid.uuid4()
        small = _make_promotion(
            company_id=company_id, name="10%",
            discount_type="PERCENTAGE", discount_value=Decimal("10"),
        )
        big = _make_promotion(
            company_id=company_id, name="R$30",
            discount_type="FIXED_AMOUNT", discount_value=Decimal("30"),
        )
        db = _make_db(promotions=[small, big])

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
        )

        assert len(result["applications"]) == 1
        assert result["applications"][0]["promotion_id"] == str(big.id)
        assert Decimal(result["discount_total"]) == Decimal("30")

    def test_only_one_exclusive_applies(self):
        company_id = uuid.uuid4()
        promos = [
            _make_promotion(company_id=company_id, discount_type="PERCENTAGE",
                            discount_value=Decimal(str(v)))
            for v in (5, 20, 10)
        ]
        db = _make_db(promotions=promos)

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("200.00"),
        )

        assert len(result["applications"]) == 1
        assert Decimal(result["discount_total"]) == Decimal("40.00")  # 20% de 200


# ─── 3. Cumulativas em sequência sobre residual ──────────────────────────────

class TestCumulativePromotions:
    def test_cumulative_applied_on_residual(self):
        company_id = uuid.uuid4()
        exclusive = _make_promotion(
            company_id=company_id, discount_type="PERCENTAGE",
            discount_value=Decimal("20"), cumulative=False,
        )
        cumulative = _make_promotion(
            company_id=company_id, discount_type="PERCENTAGE",
            discount_value=Decimal("10"), cumulative=True,
        )
        db = _make_db(promotions=[exclusive, cumulative])

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
        )

        # exclusiva: 20% de 100 = 20; cumulativa: 10% de 80 = 8 → final 72
        assert len(result["applications"]) == 2
        assert Decimal(result["applications"][0]["discount_amount"]) == Decimal("20.00")
        assert Decimal(result["applications"][1]["base_amount"]) == Decimal("80.00")
        assert Decimal(result["applications"][1]["discount_amount"]) == Decimal("8.00")
        assert Decimal(result["final_amount"]) == Decimal("72.00")
        assert result["applications"][0]["sequence"] == 1
        assert result["applications"][1]["sequence"] == 2

    def test_cumulatives_ordered_by_priority_desc(self):
        company_id = uuid.uuid4()
        low = _make_promotion(
            company_id=company_id, name="low", discount_type="FIXED_AMOUNT",
            discount_value=Decimal("10"), cumulative=True, priority=1,
        )
        high = _make_promotion(
            company_id=company_id, name="high", discount_type="FIXED_AMOUNT",
            discount_value=Decimal("10"), cumulative=True, priority=9,
        )
        db = _make_db(promotions=[low, high])

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
        )

        assert result["applications"][0]["promotion_id"] == str(high.id)
        assert result["applications"][1]["promotion_id"] == str(low.id)
        assert Decimal(result["final_amount"]) == Decimal("80.00")


# ─── 4. Cupom esgotado → 422 ─────────────────────────────────────────────────

class TestCouponExhausted:
    def test_exhausted_coupon_rejected(self):
        company_id = uuid.uuid4()
        coupon = _make_coupon(company_id=company_id, max_uses=1, uses_count=1)
        db = _make_db(promotions=[], coupon=coupon)

        with pytest.raises(HTTPException) as exc:
            promotion_service.compute_preview(
                db=db, company_id=company_id, gross_amount=Decimal("100.00"),
                coupon_code="CUPOM10",
            )
        assert exc.value.status_code == 422
        assert "esgotado" in exc.value.detail.lower()

    def test_unknown_coupon_rejected(self):
        db = _make_db(promotions=[], coupon=None)
        with pytest.raises(HTTPException) as exc:
            promotion_service.compute_preview(
                db=db, company_id=uuid.uuid4(), gross_amount=Decimal("100.00"),
                coupon_code="NAOEXISTE",
            )
        assert exc.value.status_code == 422


# ─── 5. PER_CUSTOMER usado por outro cliente → 422 ───────────────────────────

class TestPerCustomerCoupon:
    def test_other_customer_rejected(self):
        company_id = uuid.uuid4()
        owner_customer = uuid.uuid4()
        coupon = _make_coupon(
            company_id=company_id, generation_type="PER_CUSTOMER",
            customer_id=owner_customer, max_uses=None,
        )
        db = _make_db(promotions=[], coupon=coupon)

        with pytest.raises(HTTPException) as exc:
            promotion_service.compute_preview(
                db=db, company_id=company_id, gross_amount=Decimal("100.00"),
                coupon_code="CUPOM10", customer_id=uuid.uuid4(),
            )
        assert exc.value.status_code == 422
        assert "outro cliente" in exc.value.detail.lower()

    def test_owner_customer_accepted(self):
        company_id = uuid.uuid4()
        owner_customer = uuid.uuid4()
        promo = _make_promotion(
            company_id=company_id, application_mode="COUPON_REQUIRED",
            discount_type="FIXED_AMOUNT", discount_value=Decimal("5"),
        )
        coupon = _make_coupon(
            company_id=company_id, promotion_id=promo.id,
            generation_type="PER_CUSTOMER", customer_id=owner_customer,
            max_uses=None,
        )
        db = _make_db(promotions=[promo], coupon=coupon, promotion_single=promo)

        result = promotion_service.compute_preview(
            db=db, company_id=company_id, gross_amount=Decimal("100.00"),
            coupon_code="CUPOM10", customer_id=owner_customer,
        )
        assert result["coupon_valid"] is True
        assert Decimal(result["discount_total"]) == Decimal("5")


# ─── 6. Revalidação na efetivação ────────────────────────────────────────────

class TestEffectuateRevalidation:
    def test_paused_promotion_publishes_effectuation_failed(self):
        """Cupom válido mas promoção pausada entre preview e confirm:
        publica promotion.effectuation_failed e NÃO bloqueia (sem raise)."""
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        coupon = _make_coupon(company_id=company_id)
        # promoção pausada → fora da query de ACTIVE → lista vazia
        db = _make_db(promotions=[], coupon=coupon)

        with patch.object(promotion_service, "event_bus") as bus:
            result = promotion_service.effectuate(
                db=db, company_id=company_id, payment_id=payment_id,
                gross_amount=Decimal("100.00"), coupon_code="CUPOM10",
            )

        assert result is None
        published = [c.args[0].event_type for c in bus.publish.call_args_list]
        assert "promotion.effectuation_failed" in published
        db.commit.assert_not_called()
        assert coupon.uses_count == 0  # cupom NÃO redimido

    def test_invalid_coupon_publishes_effectuation_failed(self):
        """Cupom esgotado na revalidação → effectuation_failed, sem raise."""
        company_id = uuid.uuid4()
        coupon = _make_coupon(company_id=company_id, max_uses=1, uses_count=1)
        db = _make_db(promotions=[], coupon=coupon)

        with patch.object(promotion_service, "event_bus") as bus:
            result = promotion_service.effectuate(
                db=db, company_id=company_id, payment_id=uuid.uuid4(),
                gross_amount=Decimal("100.00"), coupon_code="CUPOM10",
            )

        assert result is None
        published = [c.args[0].event_type for c in bus.publish.call_args_list]
        assert published == ["promotion.effectuation_failed"]

    def test_effectuate_happy_path_redeems_and_publishes(self):
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        promo = _make_promotion(
            company_id=company_id, application_mode="COUPON_REQUIRED",
            discount_type="FIXED_AMOUNT", discount_value=Decimal("10"),
        )
        coupon = _make_coupon(company_id=company_id, promotion_id=promo.id,
                              max_uses=1, uses_count=0)
        db = _make_db(promotions=[promo], coupon=coupon)
        added = []
        db.add.side_effect = added.append

        with patch.object(promotion_service, "event_bus") as bus:
            result = promotion_service.effectuate(
                db=db, company_id=company_id, payment_id=payment_id,
                gross_amount=Decimal("100.00"), coupon_code="CUPOM10",
            )

        assert result is not None
        assert Decimal(result["discount_total"]) == Decimal("10")
        assert promo.uses_count == 1
        assert coupon.uses_count == 1
        assert coupon.status == "EXHAUSTED"  # max_uses atingido
        type_names = [type(obj).__name__ for obj in added]
        assert "DiscountApplication" in type_names
        assert "CouponRedemption" in type_names
        db.commit.assert_called_once()
        published = [c.args[0].event_type for c in bus.publish.call_args_list]
        assert "coupon.redeemed" in published
        assert "promotion.effectuated" in published

    def test_effectuate_idempotent(self):
        """DiscountApplications já existentes para o payment → no-op."""
        company_id = uuid.uuid4()
        db = _make_db(existing_application=MagicMock())

        with patch.object(promotion_service, "event_bus") as bus:
            result = promotion_service.effectuate(
                db=db, company_id=company_id, payment_id=uuid.uuid4(),
                gross_amount=Decimal("100.00"), coupon_code="CUPOM10",
            )

        assert result is None
        db.add.assert_not_called()
        db.commit.assert_not_called()
        bus.publish.assert_not_called()


# ─── 7. Race de uses_count (PostgreSQL real) ─────────────────────────────────

@pytest.mark.skipif(not DATABASE_URL, reason="Requer PostgreSQL real (DATABASE_URL)")
class TestCouponRaceCondition:
    def test_single_use_coupon_concurrent_redeem(self):
        """Dois redeems simultâneos do mesmo cupom SINGLE_USE: SELECT FOR
        UPDATE serializa — apenas um incrementa uses_count."""
        import threading
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)

        setup = Session()
        company_id = setup.execute(text("SELECT id FROM companies LIMIT 1")).scalar()
        user_id = setup.execute(text("SELECT id FROM users LIMIT 1")).scalar()
        if not company_id or not user_id:
            setup.close()
            pytest.skip("Banco sem company/user para satisfazer FKs")

        promo_id = uuid.uuid4()
        coupon_id = uuid.uuid4()
        code = f"RACE{uuid.uuid4().hex[:8].upper()}"
        setup.execute(text("""
            INSERT INTO promotions (id, company_id, name, discount_type,
                discount_value, application_mode, status, created_by)
            VALUES (:id, :cid, 'race-test', 'FIXED_AMOUNT', 10,
                'COUPON_REQUIRED', 'ACTIVE', :uid)
        """), {"id": str(promo_id), "cid": str(company_id), "uid": str(user_id)})
        setup.execute(text("""
            INSERT INTO coupons (id, company_id, promotion_id, code,
                generation_type, max_uses, uses_count, status)
            VALUES (:id, :cid, :pid, :code, 'SINGLE_USE', 1, 0, 'ACTIVE')
        """), {"id": str(coupon_id), "cid": str(company_id),
               "pid": str(promo_id), "code": code})
        setup.commit()

        results = []

        def _redeem():
            s = Session()
            try:
                row = s.execute(
                    text("SELECT uses_count, max_uses FROM coupons "
                         "WHERE id = :id FOR UPDATE"),
                    {"id": str(coupon_id)},
                ).first()
                import time
                time.sleep(0.2)  # alarga a janela de race
                if row.uses_count < row.max_uses:
                    s.execute(
                        text("UPDATE coupons SET uses_count = uses_count + 1, "
                             "status = 'EXHAUSTED' WHERE id = :id"),
                        {"id": str(coupon_id)},
                    )
                    s.commit()
                    results.append("redeemed")
                else:
                    s.rollback()
                    results.append("rejected")
            finally:
                s.close()

        try:
            threads = [threading.Thread(target=_redeem) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            final = Session()
            uses = final.execute(
                text("SELECT uses_count FROM coupons WHERE id = :id"),
                {"id": str(coupon_id)},
            ).scalar()
            final.close()

            assert uses == 1
            assert sorted(results) == ["redeemed", "rejected"]
        finally:
            cleanup = Session()
            cleanup.execute(text("DELETE FROM coupons WHERE id = :id"),
                            {"id": str(coupon_id)})
            cleanup.execute(text("DELETE FROM promotions WHERE id = :id"),
                            {"id": str(promo_id)})
            cleanup.commit()
            cleanup.close()


# ─── 8. Refund → reverted_at preenchido ──────────────────────────────────────

class TestRevertForRefund:
    def test_redemption_reverted_never_reopen(self):
        company_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        promo = _make_promotion(company_id=company_id, uses_count=1)
        application = MagicMock(promotion_id=promo.id, reverted_at=None)
        coupon = _make_coupon(
            company_id=company_id, uses_count=1, max_uses=1,
            status="EXHAUSTED", coupon_reopen_policy="NEVER_REOPEN",
        )
        redemption = MagicMock(coupon_id=coupon.id, reverted_at=None)
        db = _make_db(
            applications=[application], redemptions=[redemption],
            coupon=coupon, promotion_single=promo,
        )

        with patch.object(promotion_service, "event_bus") as bus:
            promotion_service.revert_for_refund(
                db=db, company_id=company_id, payment_id=payment_id,
            )

        assert redemption.reverted_at is not None
        assert redemption.reverted_reason == "payment.refunded"
        assert application.reverted_at is not None
        # NEVER_REOPEN: cupom permanece consumido
        assert coupon.uses_count == 1
        assert coupon.status == "EXHAUSTED"
        # promoção libera o uso
        assert promo.uses_count == 0
        db.commit.assert_called_once()
        published = [c.args[0].event_type for c in bus.publish.call_args_list]
        assert "coupon.redemption_reverted" in published
        assert "promotion.application_reverted" in published

    def test_reopen_on_refund_reactivates_coupon(self):
        company_id = uuid.uuid4()
        coupon = _make_coupon(
            company_id=company_id, uses_count=1, max_uses=1,
            status="EXHAUSTED", coupon_reopen_policy="REOPEN_ON_REFUND",
        )
        redemption = MagicMock(coupon_id=coupon.id, reverted_at=None)
        db = _make_db(redemptions=[redemption], coupon=coupon)

        with patch.object(promotion_service, "event_bus"):
            promotion_service.revert_for_refund(
                db=db, company_id=company_id, payment_id=uuid.uuid4(),
            )

        assert coupon.uses_count == 0
        assert coupon.status == "ACTIVE"


# ─── 9 + 10. manual-discount ─────────────────────────────────────────────────

class TestManualDiscount:
    def test_missing_reason_422(self):
        db = _make_db()
        with pytest.raises(HTTPException) as exc:
            payment_service.apply_manual_discount(
                payment_id=uuid.uuid4(), company_id=uuid.uuid4(),
                discount_amount=Decimal("10"), reason="   ",
                actor_id=uuid.uuid4(), db=db,
            )
        assert exc.value.status_code == 422
        assert "reason" in exc.value.detail.lower()

    def test_non_pending_payment_422(self):
        payment = _make_payment(status="CONFIRMED")
        db = _make_db(payment=payment)
        with pytest.raises(HTTPException) as exc:
            payment_service.apply_manual_discount(
                payment_id=payment.payment_id, company_id=payment.company_id,
                discount_amount=Decimal("10"), reason="cliente fiel",
                actor_id=uuid.uuid4(), db=db,
            )
        assert exc.value.status_code == 422

    def test_discount_exceeding_net_422(self):
        payment = _make_payment(gross=Decimal("50.00"))
        db = _make_db(payment=payment)
        with pytest.raises(HTTPException) as exc:
            payment_service.apply_manual_discount(
                payment_id=payment.payment_id, company_id=payment.company_id,
                discount_amount=Decimal("60"), reason="erro",
                actor_id=uuid.uuid4(), db=db,
            )
        assert exc.value.status_code == 422

    @patch("app.modules.payments.service.record_sensitive_action")
    def test_happy_path_audits_and_increments_override_count(self, mock_audit):
        payment = _make_payment(gross=Decimal("100.00"))
        company_id = payment.company_id
        db = _make_db(payment=payment, application_count=0)
        added = []
        db.add.side_effect = added.append

        result = payment_service.apply_manual_discount(
            payment_id=payment.payment_id, company_id=company_id,
            discount_amount=Decimal("25.00"), reason="cliente VIP",
            actor_id=uuid.uuid4(), db=db, actor_role="OWNER",
        )

        assert result.discount_amount == Decimal("25.00")
        assert result.net_charged_amount == Decimal("75.00")
        assert result.manual_override_count == 1
        mock_audit.assert_called_once()
        ctx = mock_audit.call_args.args[0]
        assert ctx.action == "manual_discount_override"
        assert ctx.reason == "cliente VIP"
        # DiscountApplication manual: promotion_id=None, type MANUAL
        manual_apps = [a for a in added if type(a).__name__ == "DiscountApplication"]
        assert len(manual_apps) == 1
        assert manual_apps[0].promotion_id is None
        assert manual_apps[0].discount_type == "MANUAL"
        assert manual_apps[0].base_amount_at_application == Decimal("100.00")
        db.commit.assert_called_once()

    def test_operator_forbidden_403(self):
        """RBAC: OPERATOR não pode aplicar desconto manual."""
        import inspect
        from app.modules.payments import router as payments_router_module

        # A rota usa _owner_admin como dependency de auth
        sig = inspect.signature(payments_router_module.manual_discount_payment)
        assert sig.parameters["user"].default.dependency is payments_router_module._owner_admin

        # _owner_admin rejeita OPERATOR com 403
        operator = MagicMock()
        operator.role = "OPERATOR"
        with pytest.raises(HTTPException) as exc:
            payments_router_module._owner_admin(user=operator)
        assert exc.value.status_code == 403


# ─── 11. Cross-tenant ────────────────────────────────────────────────────────

class TestCrossTenant:
    def test_promotion_of_other_company_invisible(self):
        # filtro por company_id no service: outra empresa → first() = None → 404
        db = _make_db(promotion_single=None)
        with pytest.raises(HTTPException) as exc:
            promotion_service.get_promotion(
                promotion_id=uuid.uuid4(), company_id=uuid.uuid4(), db=db,
            )
        assert exc.value.status_code == 404

    def test_coupon_of_other_company_invalid(self):
        # cupom existe na empresa A; consulta da empresa B filtra company_id → None
        db = _make_db(coupon=None)
        with pytest.raises(HTTPException) as exc:
            promotion_service.compute_preview(
                db=db, company_id=uuid.uuid4(), gross_amount=Decimal("100.00"),
                coupon_code="DAEMPRESA_A",
            )
        assert exc.value.status_code == 422


# ─── 12. DRE: desconto reduz receita ─────────────────────────────────────────

class TestDiscountInDRE:
    @patch("app.modules.payments.service.record_sensitive_action")
    def test_receita_reflects_discounted_net(self, _mock_audit):
        """Desconto manual reduz net_charged_amount; a Entry RECEITA do confirm
        usa o net — o DRE agrega a receita já líquida do desconto."""
        from app.modules.financial_core import service as financial_core

        payment = _make_payment(gross=Decimal("100.00"))
        db = _make_db(payment=payment)

        payment_service.apply_manual_discount(
            payment_id=payment.payment_id, company_id=payment.company_id,
            discount_amount=Decimal("28.00"), reason="promoção balcão",
            actor_id=uuid.uuid4(), db=db,
        )
        assert payment.net_charged_amount == Decimal("72.00")

        # Entry RECEITA lançada com o net (handle_payment_confirmed usa
        # payment.net_charged_amount) → DRE agrega o valor com desconto
        entry = MagicMock()
        entry.type = "RECEITA"
        entry.category = "SERVICOS"
        entry.amount = payment.net_charged_amount

        dre_db = MagicMock()
        dre_db.query.return_value.filter.return_value.all.return_value = [entry]

        dre = financial_core.aggregate_dre(
            company_id=payment.company_id,
            date_from=_now() - timedelta(days=1),
            date_to=_now(),
            db=dre_db,
        )
        assert dre["receita_total"] == Decimal("72.00")
        assert dre["receita"]["SERVICOS"] == Decimal("72.00")


# ─── Extras: criação de payment com cupom + FSM de promoção ──────────────────

class TestPaymentWithCoupon:
    def test_create_payment_applies_coupon_discount(self):
        company_id = uuid.uuid4()
        db = MagicMock()
        captured = []
        db.add.side_effect = captured.append

        with patch(
            "app.modules.promotions.service.compute_preview",
            return_value={"final_amount": "90.00", "discount_total": "10.00",
                          "applications": [], "coupon_valid": True},
        ):
            payment_service.create_payment(
                company_id=company_id,
                customer_id=uuid.uuid4(),
                gross_amount=Decimal("100.00"),
                payment_method="CASH",
                provider="manual",
                target_account_id=uuid.uuid4(),
                coupon_code="cupom10",
                db=db,
            )

        payments = [p for p in captured if type(p).__name__ == "Payment"]
        assert len(payments) == 1
        assert payments[0].discount_amount == Decimal("10.00")
        assert payments[0].net_charged_amount == Decimal("90.00")
        assert payments[0].coupon_code == "CUPOM10"  # normalizado uppercase


class TestPromotionFSM:
    def test_pause_from_draft_rejected(self):
        promo = _make_promotion(status="DRAFT")
        db = _make_db(promotion_single=promo)
        with pytest.raises(HTTPException) as exc:
            promotion_service.transition_promotion(
                promotion_id=promo.id, company_id=promo.company_id,
                action="pause", db=db,
            )
        assert exc.value.status_code == 422

    def test_activate_then_events_published(self):
        promo = _make_promotion(status="DRAFT")
        db = _make_db(promotion_single=promo)
        with patch.object(promotion_service, "event_bus") as bus:
            promotion_service.transition_promotion(
                promotion_id=promo.id, company_id=promo.company_id,
                action="activate", db=db,
            )
        assert promo.status == "ACTIVE"
        published = [c.args[0].event_type for c in bus.publish.call_args_list]
        assert published == ["promotion.activated"]
