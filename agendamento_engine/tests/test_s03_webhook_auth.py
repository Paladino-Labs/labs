"""
Testes do Sprint S0.3 — autenticação dos webhooks Asaas (transaction + account_status).

Contrato:
  - Token estático no header asaas-access-token (único mecanismo que o Asaas
    oferece — não há HMAC de payload).
  - FAIL-CLOSED: ASAAS_WEBHOOK_TOKEN vazio/não configurado → 401 para tudo.
  - Ausente, vazio e errado caem no MESMO 401 com o mesmo detail
    (indistinguibilidade — princípio do S0.2).
  - Comparação em tempo constante (hmac.compare_digest).
  - Log de rejeição nunca contém o token recebido.
  - Com credencial válida, o contrato do S0.1 segue intacto (gate de eventos,
    503 da corrida, 500 da falha).

Estilo unitário com mocks — mesmo padrão de test_s01_webhook_confirm.py.
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.modules.payments import router as router_module

TOKEN = "tok_s03_secreto"


def _make_payment():
    p = MagicMock()
    p.payment_id = uuid.uuid4()
    p.company_id = uuid.uuid4()
    p.status = "PENDING"
    p.net_charged_amount = Decimal("100.00")
    p.external_charge_id = "pay_abc123"
    return p


def _make_db(payment=None):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = payment
    return db


def _payload(event="PAYMENT_CONFIRMED"):
    return {
        "id": "evt_s03",
        "event": event,
        "payment": {"id": "pay_abc123", "value": "100.00", "fee": "2.00"},
    }


def _call_transaction(db, token, expected=TOKEN):
    with patch.object(router_module, "settings") as mock_settings:
        mock_settings.ASAAS_WEBHOOK_TOKEN = expected
        return router_module.webhook_asaas_transaction(
            payload=_payload(),
            asaas_access_token=token,
            db=db,
        )


def _call_account_status(db, token, expected=TOKEN):
    with patch.object(router_module, "settings") as mock_settings:
        mock_settings.ASAAS_WEBHOOK_TOKEN = expected
        return router_module.webhook_asaas_account_status(
            request=MagicMock(),
            payload={"event": "ACCOUNT_STATUS_CHANGE",
                     "account": {"id": "acc_1", "status": "ACTIVE"}},
            asaas_access_token=token,
            db=db,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 1–2. transaction — sem credencial / credencial errada → 401, nada processado
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", ["", "token_errado"])
def test_transaction_rejects_missing_and_wrong_token(token):
    db = _make_db(_make_payment())

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        with pytest.raises(HTTPException) as exc_info:
            _call_transaction(db, token)

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Token de webhook inválido"
    mock_svc.confirm.assert_not_called()
    db.query.assert_not_called()  # rejeição ANTES de qualquer processamento


def test_transaction_missing_and_wrong_are_indistinguishable():
    """Ausente, vazio e errado → mesmo status e mesmo detail (sem oráculo)."""
    exceptions = []
    for token in ["", "   ", "quase_" + TOKEN]:
        with pytest.raises(HTTPException) as exc_info:
            _call_transaction(_make_db(), token)
        exceptions.append((exc_info.value.status_code, exc_info.value.detail))

    assert len(set(exceptions)) == 1


# ─────────────────────────────────────────────────────────────────────────────
# 3. transaction — credencial correta → fluxo S0.1 processa normalmente
# ─────────────────────────────────────────────────────────────────────────────

def test_transaction_valid_token_processes_event():
    payment = _make_payment()
    db = _make_db(payment)

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        result = _call_transaction(db, TOKEN)

    assert result == {"ok": True, "event_id": "evt_s03"}
    mock_svc.confirm.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 4. FAIL-CLOSED — token NÃO configurado no ambiente → 401 para tudo
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expected", ["", "   "])
@pytest.mark.parametrize("token", ["", "qualquer_coisa"])
def test_transaction_unconfigured_token_rejects_everything(token, expected, caplog):
    """Antes (padrão do account_status), token vazio = validação desligada.
    Agora: token vazio = TUDO rejeitado, com log ERROR (falha nossa de config)."""
    db = _make_db(_make_payment())

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        with caplog.at_level("ERROR"):
            with pytest.raises(HTTPException) as exc_info:
                _call_transaction(db, token, expected=expected)

    assert exc_info.value.status_code == 401
    mock_svc.confirm.assert_not_called()
    assert any("não configurado" in r.message for r in caplog.records)
    assert all(r.levelname == "ERROR" for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Log de rejeição nunca contém o token recebido
# ─────────────────────────────────────────────────────────────────────────────

def test_rejection_log_does_not_leak_token(caplog):
    secret_attempt = "token_supersecreto_vazado"

    with caplog.at_level("WARNING"):
        with pytest.raises(HTTPException):
            _call_transaction(_make_db(), secret_attempt)

    for record in caplog.records:
        assert secret_attempt not in record.getMessage()
        # nem prefixo (o account_status antigo logava token_received[:8])
        assert secret_attempt[:8] not in record.getMessage()


def test_wrong_token_logs_warning_not_error(caplog):
    """Assimetria de severidade: token errado = WARNING (terceiro);
    token não configurado = ERROR (falha nossa) — coberto no teste 4."""
    with caplog.at_level("WARNING"):
        with pytest.raises(HTTPException):
            _call_transaction(_make_db(), "token_errado")

    assert any(r.levelname == "WARNING" for r in caplog.records)
    assert not any(r.levelname == "ERROR" for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 6–8. account_status — mesmo contrato (regressão do fail-open antigo)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", ["", "token_errado"])
def test_account_status_rejects_missing_and_wrong_token(token):
    db = _make_db()

    with pytest.raises(HTTPException) as exc_info:
        _call_account_status(db, token)

    assert exc_info.value.status_code == 401
    db.commit.assert_not_called()


def test_account_status_unconfigured_token_rejects():
    """REGRESSÃO DO FAIL-OPEN: antes, ASAAS_WEBHOOK_TOKEN vazio aceitava
    qualquer request em silêncio. Agora rejeita (fail-closed)."""
    db = _make_db()

    with pytest.raises(HTTPException) as exc_info:
        _call_account_status(db, "qualquer", expected="")

    assert exc_info.value.status_code == 401
    db.commit.assert_not_called()


def test_account_status_valid_token_processes():
    company = MagicMock()
    company.external_account_status = "pending_verification"
    db = _make_db(company)

    result = _call_account_status(db, TOKEN)

    assert result["ok"] is True
    assert company.external_account_status == "active"
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Interação S0.1 × S0.3 — autenticado, o contrato do S0.1 continua valendo
# ─────────────────────────────────────────────────────────────────────────────

def test_authenticated_request_keeps_s01_event_gate():
    db = _make_db(_make_payment())

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        with patch.object(router_module, "settings") as mock_settings:
            mock_settings.ASAAS_WEBHOOK_TOKEN = TOKEN
            result = router_module.webhook_asaas_transaction(
                payload=_payload(event="PAYMENT_OVERDUE"),
                asaas_access_token=TOKEN,
                db=db,
            )

    assert result["skipped"] == "event_not_handled"
    mock_svc.confirm.assert_not_called()


def test_authenticated_request_keeps_s01_race_503():
    db = _make_db(payment=None)  # Payment ainda não visível

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        with pytest.raises(HTTPException) as exc_info:
            _call_transaction(db, TOKEN)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "payment_not_yet_visible"
    mock_svc.confirm.assert_not_called()


def test_authenticated_request_keeps_s01_confirm_failure_500():
    db = _make_db(_make_payment())

    with patch("app.modules.payments.router.payment_service") as mock_svc:
        mock_svc.confirm.side_effect = IntegrityError("stmt", {}, Exception("x"))
        with pytest.raises(HTTPException) as exc_info:
            _call_transaction(db, TOKEN)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "confirm_failed"
