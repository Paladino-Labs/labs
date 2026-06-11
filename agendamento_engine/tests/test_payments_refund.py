"""Testes para payment_service.refund() — verificação de ordem e comportamento.

Casos cobertos:
  1. refund() em pagamento ASAAS → provider.refund() chamado ANTES do Financial Core
  2. refund() em pagamento CASH/manual → provider.refund() NÃO chamado
  3. refund() quando provider.refund() lança exceção → payment não muda status
  4. refund() em pagamento já REFUNDED → 422
  5. refund() em pagamento PENDING → 422
  6. refund() em pagamento ASAAS sem external_charge_id → sem chamada ao provider
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest

from app.modules.payments.providers.asaas import AsaasError
from app.modules.payments.service import RefundReason


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

_UNSET = object()


def _make_payment(
    payment_id=None,
    company_id=None,
    status="CONFIRMED",
    payment_method="PIX",
    provider="asaas",
    net_charged_amount=Decimal("100.00"),
    target_account_id=None,
    external_charge_id=_UNSET,
):
    p = MagicMock()
    p.payment_id = payment_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.provider = provider
    p.net_charged_amount = Decimal(str(net_charged_amount))
    p.target_account_id = target_account_id or uuid.uuid4()
    p.external_charge_id = (
        f"cha_{uuid.uuid4().hex[:12]}" if external_charge_id is _UNSET else external_charge_id
    )
    p.refunded_at = None
    p._sa_instance_state = MagicMock()
    return p


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    return db


# ─────────────────────────────────────────────────────────────────────────────
# 1. refund() ASAAS → provider.refund() chamado ANTES do Financial Core
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_asaas_calls_provider_before_financial_core():
    """provider.refund() deve ser chamado antes de financial_core.handle_payment_refunded()."""
    payment = _make_payment(provider="asaas", external_charge_id="cha_abc123")
    db = _make_db()
    call_order = []

    mock_provider = MagicMock()
    mock_provider.refund.side_effect = lambda *a, **kw: call_order.append("provider.refund")

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        mock_fc.handle_payment_refunded.side_effect = lambda *a, **kw: call_order.append("financial_core")

        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.SERVICE_FAILURE,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    assert call_order == ["provider.refund", "financial_core"], (
        f"Ordem incorreta: {call_order}. provider.refund() deve preceder financial_core."
    )
    mock_provider.refund.assert_called_once_with(
        "cha_abc123",
        RefundReason.SERVICE_FAILURE.value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. refund() CASH/manual → provider.refund() NÃO chamado
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_cash_does_not_call_provider():
    """Pagamentos CASH/manual não devem chamar provider.refund()."""
    payment = _make_payment(
        payment_method="CASH",
        provider="manual",
        external_charge_id=None,
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.REGISTRATION_ERROR,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    mock_factory.assert_not_called()


def test_refund_manual_provider_does_not_call_provider():
    """Provider=manual com payment_method não-CASH também não deve chamar provider.refund()."""
    payment = _make_payment(
        payment_method="MAQUININHA",
        provider="manual",
        external_charge_id="term_abc123",
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.OTHER,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    mock_factory.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 3. provider.refund() lança exceção → payment não muda status, DB não commitado
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_provider_exception_does_not_update_payment():
    """Se provider.refund() lançar exceção, refund() responde 502 e payment.status não muda."""
    from fastapi import HTTPException

    payment = _make_payment(provider="asaas", external_charge_id="cha_fail123")
    original_status = payment.status
    db = _make_db()

    mock_provider = MagicMock()
    mock_provider.refund.side_effect = AsaasError("gateway_error")

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action") as mock_audit,
    ):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.SERVICE_FAILURE,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 502
    assert payment.status == original_status, "Status não deve mudar após falha no provider"
    mock_fc.handle_payment_refunded.assert_not_called()
    mock_audit.assert_not_called()
    db.commit.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4. refund() em pagamento já REFUNDED → 422 idempotente
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_already_refunded_raises_422():
    """Pagamento com status REFUNDED deve retornar 422."""
    from fastapi import HTTPException

    payment = _make_payment(status="REFUNDED", provider="asaas")
    db = _make_db()

    with patch("app.modules.payments.service._get_payment", return_value=payment):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.OTHER,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "REFUNDED" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 5. refund() em pagamento PENDING → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_pending_payment_raises_422():
    """Pagamento PENDING não pode ser estornado — deve retornar 422."""
    from fastapi import HTTPException

    payment = _make_payment(status="PENDING", provider="asaas")
    db = _make_db()

    with patch("app.modules.payments.service._get_payment", return_value=payment):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.OTHER,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "CONFIRMED" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 6. refund() ASAAS sem external_charge_id → sem chamada ao provider
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_asaas_without_external_charge_id_skips_provider():
    """Pagamento provider=asaas mas sem external_charge_id não deve chamar provider.refund()."""
    payment = _make_payment(provider="asaas", external_charge_id=None)
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.SERVICE_FAILURE,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    mock_factory.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 7. refund() PagSeguro → 422 com mensagem de ação manual
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_pagseguro_raises_422():
    """refund() em pagamento PagSeguro deve levantar HTTP 422 e não chamar provider."""
    from fastapi import HTTPException

    payment = _make_payment(
        provider="pagseguro",
        payment_method="MAQUININHA",
        external_charge_id="psg_abc123",
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
    ):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.SERVICE_FAILURE,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "PagSeguro" in exc_info.value.detail
    assert "painel PagSeguro" in exc_info.value.detail
    mock_factory.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 8. refund() Asaas → provider.refund() chamado normalmente (regressão)
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_asaas_not_affected_by_pagseguro_guard():
    """Guard PagSeguro não deve afetar estorno via Asaas."""
    payment = _make_payment(provider="asaas", external_charge_id="cha_ok123")
    db = _make_db()

    mock_provider = MagicMock()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.SERVICE_FAILURE,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
        )

    mock_provider.refund.assert_called_once_with(
        "cha_ok123",
        RefundReason.SERVICE_FAILURE.value,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 9. force_local — Sprint I
# ─────────────────────────────────────────────────────────────────────────────

def test_refund_force_local_skips_provider_and_audits():
    """force_local=True pula o gateway e grava audit refund_payment_forced_local."""
    payment = _make_payment(provider="asaas", external_charge_id="cha_forced")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action") as mock_audit,
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.OTHER,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
            force_local=True,
        )

    mock_factory.assert_not_called()
    mock_fc.handle_payment_refunded.assert_called_once()
    ctx = mock_audit.call_args.args[0]
    assert ctx.action == "refund_payment_forced_local"
    assert ctx.after_snapshot == {"force_local": True, "note": "estorno forçado sem gateway"}
    assert payment.status == "REFUNDED"


def test_refund_force_local_without_reason_raises_422():
    """force_local sem reason → 422, nada persiste."""
    from fastapi import HTTPException

    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment") as mock_get,
        patch("app.modules.payments.service.financial_core") as mock_fc,
    ):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=uuid.uuid4(),
                reason=None,
                actor_id=uuid.uuid4(),
                company_id=uuid.uuid4(),
                db=db,
                force_local=True,
            )

    assert exc_info.value.status_code == 422
    mock_get.assert_not_called()
    mock_fc.handle_payment_refunded.assert_not_called()
    db.commit.assert_not_called()


def test_refund_force_local_works_even_with_pagseguro():
    """force_local permite estorno contábil mesmo para provider pagseguro (guard pulado)."""
    payment = _make_payment(
        provider="pagseguro",
        payment_method="MAQUININHA",
        external_charge_id="psg_forced",
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider") as mock_factory,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action"),
        patch("app.modules.payments.service.event_bus"),
    ):
        from app.modules.payments.service import refund

        refund(
            payment_id=payment.payment_id,
            reason=RefundReason.SERVICE_FAILURE,
            actor_id=uuid.uuid4(),
            company_id=payment.company_id,
            db=db,
            force_local=True,
        )

    mock_factory.assert_not_called()
    mock_fc.handle_payment_refunded.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 10. NullProvider — NULLPROVIDER_REFUND_OUTCOME
# ─────────────────────────────────────────────────────────────────────────────

def test_null_provider_refund_outcome_env_var(monkeypatch):
    """NULLPROVIDER_REFUND_OUTCOME=error sobrepõe o outcome do construtor."""
    from app.modules.payments.providers.null_provider import NullProvider

    provider = NullProvider(outcome="success")
    monkeypatch.setenv("NULLPROVIDER_REFUND_OUTCOME", "error")
    with pytest.raises(AsaasError):
        provider.refund("null_charge_1", "OTHER")

    monkeypatch.setenv("NULLPROVIDER_REFUND_OUTCOME", "success")
    result = provider.refund("null_charge_1", "OTHER")
    assert result["status"] == "REFUNDED"

    monkeypatch.delenv("NULLPROVIDER_REFUND_OUTCOME")
    result = provider.refund("null_charge_1", "OTHER")
    assert result["status"] == "REFUNDED"


def test_refund_with_null_provider_error_nothing_persists():
    """refund com NullProvider outcome=error → 502 e nenhum Movement/Entry."""
    from fastapi import HTTPException
    from app.modules.payments.providers.null_provider import NullProvider

    payment = _make_payment(provider="asaas", external_charge_id="null_charge_x")
    db = _make_db()
    provider = NullProvider(outcome="error")

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.get_payment_provider", return_value=provider),
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.record_sensitive_action") as mock_audit,
    ):
        from app.modules.payments.service import refund

        with pytest.raises(HTTPException) as exc_info:
            refund(
                payment_id=payment.payment_id,
                reason=RefundReason.SERVICE_FAILURE,
                actor_id=uuid.uuid4(),
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 502
    assert provider.calls[-1]["method"] == "refund"
    mock_fc.handle_payment_refunded.assert_not_called()
    mock_audit.assert_not_called()
    db.commit.assert_not_called()
