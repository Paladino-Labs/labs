"""
Testes do Sprint S0.1 — Webhook Asaas + confirm(): parar de perder pagamento sem rastro.

Cobre os dois defeitos do A4 §2.1/§2.2 e o gate de tipo de evento:

  Defeito A (service.confirm):
    1. Duplicata legítima: IntegrityError no INSERT do evento + Payment CONFIRMED
       no banco → retorna Payment, sem commit, sem financial_core.
    2. IntegrityError com Payment NÃO CONFIRMED → propaga (não é duplicata benigna).
    3. Falha do Financial Core (IntegrityError no passo 4) → propaga, rollback,
       mark_processed não chamado.

  Defeito B (router.webhook_asaas_transaction):
    4. confirm() falha → HTTPException 500 (Asaas reenvia).
    5. Payment não encontrado (corrida webhook × commit) → HTTPException 503.
    6. Gate de evento: PAYMENT_CREATED/PAYMENT_OVERDUE → 200 skipped, confirm
       NÃO chamado.
    7. Payload sem event_id → 200 skipped (comportamento preservado).

Estilo unitário com mocks — mesmo padrão de test_sprint9_payments.py.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (padrão test_sprint9_payments.py)
# ─────────────────────────────────────────────────────────────────────────────

def _make_payment(status="PENDING", payment_method="PIX"):
    p = MagicMock()
    p.payment_id = uuid.uuid4()
    p.company_id = uuid.uuid4()
    p.customer_id = uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.provider = "asaas"
    p.net_charged_amount = Decimal("100.00")
    p.provider_fee = Decimal("0.00")
    p.target_account_id = uuid.uuid4()
    p.external_charge_id = "pay_abc123"
    return p


def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _integrity_error():
    return IntegrityError("stmt", {}, Exception("unique"))


# ─────────────────────────────────────────────────────────────────────────────
# 1. confirm() — duplicata legítima: IntegrityError + Payment CONFIRMED no banco
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_duplicate_event_with_confirmed_payment_returns_payment():
    """IntegrityError no evento + Payment CONFIRMED no banco = duplicata benigna."""
    payment = _make_payment(status="PENDING")
    confirmed = _make_payment(status="CONFIRMED")
    db = _make_db()
    db.flush.side_effect = _integrity_error()
    db.query.return_value.filter.return_value.first.return_value = confirmed

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed") as mock_mark,
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        result = confirm(
            payment_id=payment.payment_id,
            event_id="evt_dup",
            webhook_data={"id": "evt_dup"},
            company_id=payment.company_id,
            db=db,
        )

    assert result is confirmed
    assert result.status == "CONFIRMED"
    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    mock_fc.handle_payment_confirmed.assert_not_called()
    mock_mark.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 2. confirm() — IntegrityError mas Payment NÃO CONFIRMED → propaga (Defeito A)
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_integrity_error_with_pending_payment_propagates(caplog):
    """IntegrityError sem Payment CONFIRMED não é duplicata — deve propagar."""
    payment = _make_payment(status="PENDING")
    still_pending = _make_payment(status="PENDING")
    db = _make_db()
    db.flush.side_effect = _integrity_error()
    db.query.return_value.filter.return_value.first.return_value = still_pending

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        with caplog.at_level("ERROR"), pytest.raises(IntegrityError):
            confirm(
                payment_id=payment.payment_id,
                event_id="evt_fk_fail",
                webhook_data={"id": "evt_fk_fail"},
                company_id=payment.company_id,
                db=db,
            )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    assert any("não é duplicata benigna" in r.message for r in caplog.records)


def test_confirm_integrity_error_with_missing_payment_propagates():
    """IntegrityError e Payment sumiu do banco → propaga (nunca 'sucesso')."""
    payment = _make_payment(status="PENDING")
    db = _make_db()
    db.flush.side_effect = _integrity_error()
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
    ):
        MockTxn.return_value = MagicMock()
        from app.modules.payments.service import confirm

        with pytest.raises(IntegrityError):
            confirm(
                payment_id=payment.payment_id,
                event_id="evt_gone",
                webhook_data={"id": "evt_gone"},
                company_id=payment.company_id,
                db=db,
            )


# ─────────────────────────────────────────────────────────────────────────────
# 3. confirm() — IntegrityError do Financial Core (passo 4) → propaga
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_financial_core_integrity_error_propagates(caplog):
    """Violação de integridade DENTRO do Financial Core não é mais engolida
    como duplicata: propaga, com rollback e log de contexto."""
    payment = _make_payment(status="PENDING")
    db = _make_db()

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed") as mock_mark,
    ):
        MockTxn.return_value = MagicMock()
        mock_fc.handle_payment_confirmed.side_effect = _integrity_error()
        from app.modules.payments.service import confirm

        with caplog.at_level("ERROR"), pytest.raises(IntegrityError):
            confirm(
                payment_id=payment.payment_id,
                event_id="evt_fc_fk",
                webhook_data={"id": "evt_fc_fk"},
                company_id=payment.company_id,
                db=db,
            )

    db.rollback.assert_called_once()
    db.commit.assert_not_called()
    mock_mark.assert_not_called()
    assert any("falha nos passos 3-5" in r.message for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# Router — helpers
# ─────────────────────────────────────────────────────────────────────────────

def _webhook_payload(event="PAYMENT_CONFIRMED", charge_id="pay_abc123"):
    return {
        "id": "evt_router",
        "event": event,
        "payment": {"id": charge_id, "value": "100.00", "fee": "2.00"},
    }


_WEBHOOK_TOKEN = "tok_s01"


def _call_webhook(payload, db):
    """S0.3: o endpoint passou a exigir o header asaas-access-token (fail-closed).

    Estes testes autenticam com token válido — o contrato do S0.1 sob teste
    (gate de eventos, 503 da corrida, 500 da falha) é o mesmo; só a credencial
    foi acrescentada. Casos de rejeição vivem em test_s03_webhook_auth.py.
    """
    from app.modules.payments import router as router_module

    with patch.object(router_module, "settings") as mock_settings:
        mock_settings.ASAAS_WEBHOOK_TOKEN = _WEBHOOK_TOKEN
        return router_module.webhook_asaas_transaction(
            payload=payload,
            asaas_access_token=_WEBHOOK_TOKEN,
            db=db,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 4. Router — confirm() falha → HTTPException 500 (Defeito B)
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_confirm_failure_returns_500():
    payment = _make_payment()
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = payment

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        mock_svc.confirm.side_effect = _integrity_error()

        with pytest.raises(HTTPException) as exc_info:
            _call_webhook(_webhook_payload(), db)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "confirm_failed"


# ─────────────────────────────────────────────────────────────────────────────
# 5. Router — payment não encontrado (corrida) → HTTPException 503
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_payment_not_found_returns_503():
    """Webhook de confirmação que chega antes do commit da linha Payment deve
    responder não-2xx para o Asaas reenviar — antes era 200 e o evento se perdia."""
    db = _make_db()  # first() → None: payment não existe ainda

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        with pytest.raises(HTTPException) as exc_info:
            _call_webhook(_webhook_payload(), db)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "payment_not_yet_visible"
    mock_svc.confirm.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Router — gate de tipo de evento
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("event", ["PAYMENT_CREATED", "PAYMENT_OVERDUE", "PAYMENT_UPDATED", ""])
def test_webhook_non_confirmation_event_skipped(event):
    """Eventos que não confirmam pagamento nunca chamam confirm() — antes,
    QUALQUER evento com id confirmava o Payment."""
    payment = _make_payment()
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = payment

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        result = _call_webhook(_webhook_payload(event=event), db)

    assert result["ok"] is True
    assert result["skipped"] == "event_not_handled"
    mock_svc.confirm.assert_not_called()


@pytest.mark.parametrize("event", ["PAYMENT_RECEIVED", "PAYMENT_CONFIRMED"])
def test_webhook_confirmation_events_call_confirm(event):
    payment = _make_payment()
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = payment

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        result = _call_webhook(_webhook_payload(event=event), db)

    assert result == {"ok": True, "event_id": "evt_router"}
    mock_svc.confirm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Router — payload sem event_id → 200 skipped (preservado)
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_missing_event_id_skipped():
    db = _make_db()

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        result = _call_webhook({"event": "PAYMENT_CONFIRMED"}, db)

    assert result == {"ok": True, "skipped": "missing_event_id"}
    mock_svc.confirm.assert_not_called()
