"""Testes de confirmação manual síncrona de pagamentos CASH e MAQUININHA.

confirm_manual() retorna tuple (Payment, fee_warning_dict | None).
fee_warning_dict não-None → taxa não configurada (code="fee_not_configured").

Casos cobertos:
  1.  create_payment(method="CASH") → external_charge_id=None, status=PENDING
  2.  confirm_manual() → (Payment CONFIRMED, None), paid_at preenchido
  3.  Movement INFLOW criado em target_account após confirm_manual
  4.  confirm_manual em Payment PIX → 422 (método não-manual bloqueado)
  5.  confirm_manual em Payment CASH já CONFIRMED + is_processed=True → idempotente
  6.  confirm_manual em Payment CASH já CONFIRMED + is_processed=False → 422
  7.  EventBus payment.confirmed emitido após confirm_manual
  8.  confirm_manual chama confirm() com event_id determinístico (f"manual-{id}")
  9.  confirm_manual em Payment provider=manual → permitido
  10. webhook_data sintético usa net_charged_amount e fee="0" para CASH
  11. fee_source=None para CASH (sem routing de taxa)
  12. confirm_manual MAQUININHA_CREDIT com política 3.99% → fee calculado, sem warning
  13. confirm_manual MAQUININHA sem política → fee=0 + fee_warning present
  14. confirm_manual MAQUININHA_DEBIT usa política MAQUININHA_DEBIT
  15. confirm_manual MAQUININHA_PIX sem taxa configurada → CONFIRMED + fee_warning
  16. confirm_manual MAQUININHA_PIX com taxa 0.99% → fee=0.99 + sem warning
"""
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_payment(
    payment_id=None,
    company_id=None,
    status="PENDING",
    payment_method="CASH",
    provider="manual",
    net_charged_amount=Decimal("100.00"),
    gross_catalog_amount=None,
    provider_fee=Decimal("0.00"),
    target_account_id=None,
    external_charge_id=None,
):
    p = MagicMock()
    p.payment_id = payment_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.provider = provider
    p.net_charged_amount = Decimal(str(net_charged_amount))
    # gross_catalog_amount defaults to net_charged_amount (sem desconto)
    p.gross_catalog_amount = (
        Decimal(str(gross_catalog_amount)) if gross_catalog_amount is not None
        else Decimal(str(net_charged_amount))
    )
    p.provider_fee = Decimal(str(provider_fee))
    p.target_account_id = target_account_id or uuid.uuid4()
    p.external_charge_id = external_charge_id
    p.paid_at = None
    p._sa_instance_state = MagicMock()
    p._sa_instance_state.has_identity = False
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
# 1. create_payment com CASH → external_charge_id=None, status=PENDING
# ─────────────────────────────────────────────────────────────────────────────

def test_create_payment_cash_no_external_charge_id():
    """create_payment com payment_method=CASH não deve preencher external_charge_id."""
    company_id = uuid.uuid4()
    account_id = uuid.uuid4()
    db = _make_db()

    expected = _make_payment(
        company_id=company_id,
        status="PENDING",
        payment_method="CASH",
        provider="manual",
        net_charged_amount=Decimal("50.00"),
        target_account_id=account_id,
        external_charge_id=None,
    )
    db.refresh.side_effect = lambda obj: None

    with patch("app.modules.payments.service.Payment") as MockPayment:
        MockPayment.return_value = expected
        from app.modules.payments.service import create_payment

        result = create_payment(
            company_id=company_id,
            customer_id=None,
            gross_amount=Decimal("50.00"),
            payment_method="CASH",
            provider="manual",
            target_account_id=account_id,
            db=db,
        )

    assert result.status == "PENDING"
    assert result.external_charge_id is None
    db.add.assert_called_once()
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 2. confirm_manual → Payment CONFIRMED, paid_at preenchido
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_confirms_cash_payment():
    """confirm_manual deve chamar confirm() e retornar (Payment CONFIRMED, None)."""
    payment = _make_payment(status="PENDING", payment_method="CASH", provider="manual")
    db = _make_db()

    confirmed_payment = _make_payment(
        payment_id=payment.payment_id,
        company_id=payment.company_id,
        status="CONFIRMED",
        payment_method="CASH",
        provider="manual",
    )
    confirmed_payment.paid_at = datetime.now(timezone.utc)

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=confirmed_payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    assert confirmed.status == "CONFIRMED"
    assert confirmed.paid_at is not None
    assert fee_warning is None  # CASH nunca tem aviso
    mock_confirm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Movement INFLOW criado em target_account após confirm_manual
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_creates_inflow_movement():
    """confirm_manual deve resultar em Movement INFLOW via handle_payment_confirmed."""
    account_id = uuid.uuid4()
    payment = _make_payment(
        status="PENDING",
        payment_method="CASH",
        provider="manual",
        net_charged_amount=Decimal("80.00"),
        target_account_id=account_id,
    )
    db = _make_db()

    inflow_movement = MagicMock()
    inflow_movement.movement_id = uuid.uuid4()
    inflow_movement.type = "INFLOW"
    inflow_movement.amount = Decimal("80.00")
    inflow_movement.account_id = account_id

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus"),
    ):
        MockTxn.return_value = MagicMock()
        mock_fc.handle_payment_confirmed.return_value = {
            "inflow_movement_id": inflow_movement.movement_id,
            "receita_entry_id": uuid.uuid4(),
            "outflow_movement_id": None,
            "taxa_entry_id": None,
        }

        from app.modules.payments.service import confirm_manual

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    mock_fc.handle_payment_confirmed.assert_called_once()
    call_kwargs = mock_fc.handle_payment_confirmed.call_args.kwargs
    assert call_kwargs["gross_amount"] == Decimal("80.00")
    assert call_kwargs["target_account_id"] == account_id
    assert call_kwargs["fee_source"] is None  # CASH → sem fee_source


# ─────────────────────────────────────────────────────────────────────────────
# 4. confirm_manual em Payment PIX → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_rejects_pix():
    """confirm_manual deve rejeitar pagamentos não-CASH/non-manual com 422."""
    from fastapi import HTTPException

    payment = _make_payment(status="PENDING", payment_method="PIX", provider="asaas")
    db = _make_db()

    with patch("app.modules.payments.service._get_payment", return_value=payment):
        from app.modules.payments.service import confirm_manual

        with pytest.raises(HTTPException) as exc_info:
            confirm_manual(
                payment_id=payment.payment_id,
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "CASH" in exc_info.value.detail or "manual" in exc_info.value.detail


def test_confirm_manual_rejects_boleto():
    """confirm_manual deve rejeitar BOLETO com 422."""
    from fastapi import HTTPException

    payment = _make_payment(status="PENDING", payment_method="BOLETO", provider="asaas")
    db = _make_db()

    with patch("app.modules.payments.service._get_payment", return_value=payment):
        from app.modules.payments.service import confirm_manual

        with pytest.raises(HTTPException) as exc_info:
            confirm_manual(
                payment_id=payment.payment_id,
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422


# ─────────────────────────────────────────────────────────────────────────────
# 5. confirm_manual em Payment CASH já CONFIRMED + is_processed=True → idempotente
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_idempotent_when_already_confirmed():
    """Re-submit de confirm_manual em Payment CONFIRMED deve retornar (payment, None) sem erro."""
    payment = _make_payment(status="CONFIRMED", payment_method="CASH", provider="manual")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=True) as mock_is_proc,
        patch("app.modules.payments.service.confirm") as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    assert confirmed is payment
    assert confirmed.status == "CONFIRMED"
    assert fee_warning is None  # retorno idempotente não recalcula warning
    mock_confirm.assert_not_called()
    mock_is_proc.assert_called_once_with(
        key=f"manual-{payment.payment_id}",
        consumer="payment_confirmed",
        db=db,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 6. confirm_manual em Payment CASH CONFIRMED + is_processed=False → 422
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_rejects_confirmed_without_idempotency_key():
    """Payment CONFIRMED sem is_processed registrado deve retornar 422."""
    from fastapi import HTTPException

    payment = _make_payment(status="CONFIRMED", payment_method="CASH", provider="manual")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
    ):
        from app.modules.payments.service import confirm_manual

        with pytest.raises(HTTPException) as exc_info:
            confirm_manual(
                payment_id=payment.payment_id,
                company_id=payment.company_id,
                db=db,
            )

    assert exc_info.value.status_code == 422
    assert "PENDING" in exc_info.value.detail


# ─────────────────────────────────────────────────────────────────────────────
# 7. EventBus payment.confirmed emitido após confirm_manual
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_emits_payment_confirmed_event():
    """confirm_manual deve emitir payment.confirmed via EventBus após commit."""
    payment = _make_payment(status="PENDING", payment_method="CASH", provider="manual")
    db = _make_db()
    commit_happened = []
    published = []

    def track_commit():
        commit_happened.append(True)

    db.commit.side_effect = track_commit

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core"),
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus") as mock_bus,
    ):
        MockTxn.return_value = MagicMock()

        def capture_publish(event):
            assert len(commit_happened) == 1, "publish chamado antes do commit!"
            published.append(event.event_type)

        mock_bus.publish.side_effect = capture_publish

        from app.modules.payments.service import confirm_manual

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    assert "payment.confirmed" in published


# ─────────────────────────────────────────────────────────────────────────────
# 8. event_id determinístico f"manual-{payment_id}"
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_uses_deterministic_event_id():
    """confirm_manual deve usar event_id=f'manual-{payment_id}' para idempotência."""
    payment = _make_payment(status="PENDING", payment_method="CASH", provider="manual")
    db = _make_db()
    expected_event_id = f"manual-{payment.payment_id}"

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    mock_confirm.assert_called_once()
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["event_id"] == expected_event_id


# ─────────────────────────────────────────────────────────────────────────────
# 9. provider=manual (não-CASH) → permitido
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_allows_manual_provider():
    """provider=manual deve ser aceito independente de payment_method."""
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA",  # não é CASH, mas provider é manual
        provider="manual",
    )
    db = _make_db()

    confirmed = _make_payment(
        payment_id=payment.payment_id,
        company_id=payment.company_id,
        status="CONFIRMED",
        payment_method="MAQUININHA",
        provider="manual",
    )

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=confirmed),
    ):
        from app.modules.payments.service import confirm_manual

        confirmed_payment, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    assert confirmed_payment.status == "CONFIRMED"


# ─────────────────────────────────────────────────────────────────────────────
# 10. webhook_data sintético usa net_charged_amount e fee="0"
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_webhook_data_uses_net_amount_and_zero_fee():
    """webhook_data para confirm() deve ter value=net_charged_amount e fee='0'."""
    payment = _make_payment(
        status="PENDING",
        payment_method="CASH",
        provider="manual",
        net_charged_amount=Decimal("123.45"),
    )
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["value"] == "123.45"
    assert call_kwargs["webhook_data"]["fee"] == "0"


# ─────────────────────────────────────────────────────────────────────────────
# 11. fee_source=None para CASH (sem routing de taxa)
# ─────────────────────────────────────────────────────────────────────────────

def test_fee_source_is_none_for_cash():
    """_fee_source_for("CASH") deve retornar None."""
    from app.modules.payments.service import _fee_source_for

    assert _fee_source_for("CASH") is None
    assert _fee_source_for("cash") is None


# ─────────────────────────────────────────────────────────────────────────────
# 15. confirm_manual MAQUININHA_PIX sem taxa configurada → CONFIRMED + fee_warning
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_pix_without_fee_configured_triggers_warning():
    """MAQUININHA_PIX com fee_percentage=NULL → CONFIRMED com fee=0 e fee_warning."""
    gross = Decimal("100.00")
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA_PIX",
        provider="manual",
        gross_catalog_amount=gross,
        net_charged_amount=gross,
    )
    db = _make_db()

    # Política existe (is_active=True) mas fee_percentage=NULL (não configurado)
    policy = MagicMock()
    policy.is_active = True
    policy.fee_percentage = None
    policy.fee_flat = Decimal("0")
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed_payment, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    # Pagamento é confirmado normalmente (fee=0)
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "0"

    # Aviso presente com dados corretos
    assert fee_warning is not None
    assert fee_warning["code"] == "fee_not_configured"
    assert fee_warning["fee_source"] == "MAQUININHA_PIX"
    assert fee_warning["fee_applied"] == 0.0
    assert "PIX na maquininha" in fee_warning["message"]
    assert "Configurações" in fee_warning["message"]


# ─────────────────────────────────────────────────────────────────────────────
# 16. confirm_manual MAQUININHA_PIX com taxa 0.99% → fee calculado + sem warning
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_pix_with_fee_configured():
    """MAQUININHA_PIX com fee_percentage=0.99% → fee=0.99 e fee_warning=None."""
    gross = Decimal("100.00")
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA_PIX",
        provider="manual",
        gross_catalog_amount=gross,
        net_charged_amount=gross,
    )
    db = _make_db()

    policy = MagicMock()
    policy.is_active = True
    policy.fee_percentage = Decimal("0.99")
    policy.fee_flat = Decimal("0")
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed_payment, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    # fee = 100.00 * 0.99 / 100 = 0.99
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "0.99"
    assert fee_warning is None  # taxa configurada → sem aviso


# ─────────────────────────────────────────────────────────────────────────────
# 12. confirm_manual MAQUININHA_CREDIT com política 3.99% → fee calculado
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_credit_fee_calculated():
    """confirm_manual MAQUININHA_CREDIT com política 3.99% → fee = gross * 0.0399, sem warning."""
    gross = Decimal("100.00")
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA",
        provider="manual",
        net_charged_amount=gross,
        gross_catalog_amount=gross,
    )
    db = _make_db()

    policy = MagicMock()
    policy.is_active = True
    policy.fee_percentage = Decimal("3.99")
    policy.fee_flat = Decimal("0")
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed_payment, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "3.99"
    assert fee_warning is None  # política configurada → sem aviso


# ─────────────────────────────────────────────────────────────────────────────
# 13. confirm_manual MAQUININHA sem política ativa → fee=0 (gracioso)
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_without_active_policy_uses_zero_fee():
    """confirm_manual MAQUININHA sem política → fee=0 + fee_warning presente."""
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA",
        provider="manual",
        gross_catalog_amount=Decimal("100.00"),
    )
    db = _make_db()
    # _make_db() retorna None para qualquer db.query().filter().first()
    # → política não encontrada → fee=0 + warning

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirmed_payment, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "0"
    assert fee_warning is not None
    assert fee_warning["code"] == "fee_not_configured"
    assert fee_warning["fee_source"] == "MAQUININHA_CREDIT"


# ─────────────────────────────────────────────────────────────────────────────
# 14. confirm_manual MAQUININHA_DEBIT usa política MAQUININHA_DEBIT
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_debit_uses_debit_policy():
    """confirm_manual MAQUININHA_DEBIT calcula fee com política MAQUININHA_DEBIT (1.5%)."""
    gross = Decimal("200.00")
    payment = _make_payment(
        status="PENDING",
        payment_method="MAQUININHA_DEBIT",
        provider="manual",
        gross_catalog_amount=gross,
        net_charged_amount=gross,
    )
    db = _make_db()

    policy = MagicMock()
    policy.is_active = True
    policy.fee_percentage = Decimal("1.5")
    policy.fee_flat = Decimal("0")
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=payment.company_id,
            db=db,
        )

    # fee = 200 * 1.5 / 100 = 3.00
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "3.00"
