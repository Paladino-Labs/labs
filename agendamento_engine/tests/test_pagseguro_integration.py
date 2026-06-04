"""PagSeguro Point integration tests.

Casos cobertos:
  1.  create_charge() com terminal_id → payload inclui device_id correto
  2.  create_charge() sem terminal_id → PagSeguroError levantado
  3.  create_charge() converte amount Decimal → centavos corretamente
  4.  handle_webhook() terminal aprovado (status=PAID)    → CONFIRMED
  5.  handle_webhook() terminal cancelado (status=CANCELED) → CANCELLED
  6.  handle_webhook() status DECLINED → CANCELLED
  7.  handle_webhook() status desconhecido (WAITING) → mantém original
  8.  list_terminals() → lista retornada do mock
  9.  list_terminals() → lista vazia quando GET /devices falha
  10. GET /payments/terminals com credencial PAGSEGURO ativa → lista de terminais
  11. GET /payments/terminals sem credencial PAGSEGURO → lista vazia
  12. Factory: company com PAGSEGURO credential → PagSeguroProvider (regressão)
  13. Factory: company sem credential → AsaasProvider (fallback)
  14. Migration ORM: credentialprovider aceita 'PAGSEGURO'
  15. create_charge() não usa PIX/boleto (payment_method=CARD_CREDIT → CREDIT)
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    db.begin_nested.return_value.__enter__ = MagicMock(return_value=None)
    db.begin_nested.return_value.__exit__ = MagicMock(return_value=False)
    return db


def _make_pagseguro_provider():
    """Instancia PagSeguroProvider sem __init__ real (sem HTTP + DB)."""
    from app.modules.payments.providers.pagseguro import PagSeguroProvider

    provider = PagSeguroProvider.__new__(PagSeguroProvider)
    provider._base_url = "https://sandbox.api.pagseguro.com"
    provider._access_token = "test_access_token"
    return provider


def _terminal_charge_response(
    charge_id: str = "CHAR_TERM001",
    order_id: str = "ORDE_ORDER001",
    status: str = "WAITING",
) -> dict:
    return {
        "id": order_id,
        "charges": [
            {
                "id": charge_id,
                "status": status,
                "amount": {"value": 5000, "currency": "BRL"},
                "payment_method": {"type": "CREDIT"},
            }
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. create_charge() com terminal_id → payload inclui device_id
# ─────────────────────────────────────────────────────────────────────────────

def test_create_charge_terminal_id_in_payload():
    """terminal_id kwarg deve aparecer como device_id no payload enviado."""
    provider = _make_pagseguro_provider()
    terminal_id = "TERM_ABC123"
    captured = {}

    def fake_post(path, body):
        captured.update(body)
        return _terminal_charge_response()

    with patch.object(provider, "_post", side_effect=fake_post):
        result = provider.create_charge(
            amount=Decimal("50.00"),
            customer={"name": "Loja Teste"},
            payment_method="CARD_CREDIT",
            terminal_id=terminal_id,
            description="Corte + escova",
        )

    assert captured["charges"][0]["device_id"] == terminal_id, (
        f"device_id ausente ou incorreto no payload: {captured}"
    )
    assert result["terminal_id"] == terminal_id
    assert result["id"] == "CHAR_TERM001"
    assert result["order_id"] == "ORDE_ORDER001"


# ─────────────────────────────────────────────────────────────────────────────
# 2. create_charge() sem terminal_id → PagSeguroError
# ─────────────────────────────────────────────────────────────────────────────

def test_create_charge_without_terminal_id_raises():
    """Ausência de terminal_id deve levantar PagSeguroError."""
    from app.modules.payments.providers.pagseguro import PagSeguroError

    provider = _make_pagseguro_provider()

    with pytest.raises(PagSeguroError, match="terminal_id"):
        provider.create_charge(
            amount=Decimal("10.00"),
            customer={},
            payment_method="CARD_CREDIT",
            # sem terminal_id
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. create_charge() converte Decimal → centavos
# ─────────────────────────────────────────────────────────────────────────────

def test_create_charge_decimal_to_centavos():
    """Decimal('75.50') → amount.value = 7550 no payload."""
    provider = _make_pagseguro_provider()
    captured = {}

    def fake_post(path, body):
        captured.update(body)
        return _terminal_charge_response()

    with patch.object(provider, "_post", side_effect=fake_post):
        result = provider.create_charge(
            amount=Decimal("75.50"),
            customer={},
            payment_method="CARD_DEBIT",
            terminal_id="TERM_X",
        )

    assert captured["charges"][0]["amount"]["value"] == 7550
    assert captured["charges"][0]["amount"]["currency"] == "BRL"
    assert result["amount_centavos"] == 7550


# ─────────────────────────────────────────────────────────────────────────────
# 4. handle_webhook() PAID → CONFIRMED
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_webhook_paid_normalizes_to_confirmed():
    """charges[].status='PAID' → result['status'] = 'CONFIRMED'."""
    provider = _make_pagseguro_provider()

    payload = {
        "id": "ORDE_TERM_PAID",
        "charges": [{"id": "CHAR_TERM_PAID", "status": "PAID"}],
    }

    result = provider.handle_webhook(payload)

    assert result["event"] == "PAID"
    assert result["status"] == "CONFIRMED", f"esperado CONFIRMED, obteve: {result['status']}"
    assert result["external_id"] == "CHAR_TERM_PAID"
    assert result["raw"] is payload


# ─────────────────────────────────────────────────────────────────────────────
# 5. handle_webhook() CANCELED → CANCELLED
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_webhook_canceled_normalizes_to_cancelled():
    """charges[].status='CANCELED' → result['status'] = 'CANCELLED'."""
    provider = _make_pagseguro_provider()

    payload = {
        "id": "ORDE_TERM_CANCEL",
        "charges": [{"id": "CHAR_TERM_CANCEL", "status": "CANCELED"}],
    }

    result = provider.handle_webhook(payload)

    assert result["status"] == "CANCELLED"
    assert result["external_id"] == "CHAR_TERM_CANCEL"


# ─────────────────────────────────────────────────────────────────────────────
# 6. handle_webhook() DECLINED → CANCELLED
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_webhook_declined_normalizes_to_cancelled():
    """charges[].status='DECLINED' (cartão recusado) → 'CANCELLED'."""
    provider = _make_pagseguro_provider()

    payload = {
        "id": "ORDE_DECLINED",
        "charges": [{"id": "CHAR_DECLINED", "status": "DECLINED"}],
    }

    result = provider.handle_webhook(payload)

    assert result["status"] == "CANCELLED"
    assert result["event"] == "DECLINED"


# ─────────────────────────────────────────────────────────────────────────────
# 7. handle_webhook() status desconhecido → passthrough
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_webhook_unknown_status_passthrough():
    """Status não mapeado (WAITING) é retornado sem modificação."""
    provider = _make_pagseguro_provider()

    payload = {
        "id": "ORDE_WAITING",
        "charges": [{"id": "CHAR_WAITING", "status": "WAITING"}],
    }

    result = provider.handle_webhook(payload)

    assert result["status"] == "WAITING"
    assert result["event"] == "WAITING"


# ─────────────────────────────────────────────────────────────────────────────
# 8. list_terminals() → lista retornada do mock
# ─────────────────────────────────────────────────────────────────────────────

def test_list_terminals_returns_list():
    """list_terminals() deve retornar lista normalizada de terminais."""
    provider = _make_pagseguro_provider()

    mock_response = {
        "devices": [
            {"id": "TERM_001", "serial": "SN123456", "model": "Moderninha Pro", "status": "ACTIVE"},
            {"id": "TERM_002", "serial": "SN789012", "model": "Minizinha", "status": "ACTIVE"},
        ]
    }

    db = _make_db()

    with patch.object(provider, "_get", return_value=mock_response):
        result = provider.list_terminals(company_id=uuid.uuid4(), db=db)

    assert len(result) == 2
    assert result[0]["id"] == "TERM_001"
    assert result[0]["serial"] == "SN123456"
    assert result[0]["model"] == "Moderninha Pro"
    assert result[1]["id"] == "TERM_002"


# ─────────────────────────────────────────────────────────────────────────────
# 9. list_terminals() → [] quando GET /devices falha
# ─────────────────────────────────────────────────────────────────────────────

def test_list_terminals_returns_empty_on_error():
    """list_terminals() retorna [] quando o endpoint falha (stub/404)."""
    from app.modules.payments.providers.pagseguro import PagSeguroError

    provider = _make_pagseguro_provider()
    db = _make_db()

    with patch.object(provider, "_get", side_effect=PagSeguroError("endpoint not found")):
        result = provider.list_terminals(company_id=uuid.uuid4(), db=db)

    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 10. GET /payments/terminals com PAGSEGURO credential → lista de terminais
# ─────────────────────────────────────────────────────────────────────────────

def test_router_list_terminals_with_pagseguro_provider():
    """GET /payments/terminals com provider PagSeguro → retorna lista."""
    from app.modules.payments.router import list_payment_terminals

    provider = _make_pagseguro_provider()
    mock_terminals = [
        {"id": "TERM_001", "serial": "SN001", "model": "Moderninha Pro", "status": "ACTIVE"}
    ]

    mock_user = MagicMock()
    mock_user.company_id = uuid.uuid4()

    db = _make_db()

    # get_payment_provider é importado localmente na função do router —
    # patch no módulo factory (onde o símbolo existe de fato).
    with (
        patch(
            "app.modules.payments.provider_factory.get_payment_provider",
            return_value=provider,
        ),
        patch.object(provider, "list_terminals", return_value=mock_terminals),
    ):
        result = list_payment_terminals(user=mock_user, db=db)

    assert result == mock_terminals


# ─────────────────────────────────────────────────────────────────────────────
# 11. GET /payments/terminals sem PAGSEGURO credential → lista vazia
# ─────────────────────────────────────────────────────────────────────────────

def test_router_list_terminals_without_pagseguro_returns_empty():
    """GET /payments/terminals com AsaasProvider → [] (sem terminais Point)."""
    from app.modules.payments.providers.asaas import AsaasProvider
    from app.modules.payments.router import list_payment_terminals

    mock_asaas = MagicMock(spec=AsaasProvider)
    mock_user = MagicMock()
    mock_user.company_id = uuid.uuid4()
    db = _make_db()

    # Mesma razão: get_payment_provider é importado localmente na função do router.
    with patch(
        "app.modules.payments.provider_factory.get_payment_provider",
        return_value=mock_asaas,
    ):
        result = list_payment_terminals(user=mock_user, db=db)

    assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# 12. Factory: PAGSEGURO credential → PagSeguroProvider (regressão)
# ─────────────────────────────────────────────────────────────────────────────

def test_factory_pagseguro_credential_returns_pagseguro_provider():
    """Credential PAGSEGURO ativa → get_payment_provider retorna PagSeguroProvider."""
    from app.modules.payments.providers.pagseguro import PagSeguroProvider

    db = _make_db()
    company_id = uuid.uuid4()

    pagseguro_cred = MagicMock()
    pagseguro_cred.provider = "PAGSEGURO"
    pagseguro_cred.status = "ACTIVE"
    db.query.return_value.filter.return_value.first.return_value = pagseguro_cred

    with (
        patch(
            "app.modules.payments.providers.pagseguro._resolve_credentials",
            return_value=("cid", "csecret", "https://sandbox.api.pagseguro.com"),
        ),
        patch.object(PagSeguroProvider, "_authenticate", return_value="tok"),
    ):
        from app.modules.payments.provider_factory import get_payment_provider
        provider = get_payment_provider(company_id=company_id, db=db)

    assert isinstance(provider, PagSeguroProvider)


# ─────────────────────────────────────────────────────────────────────────────
# 13. Factory: sem credential → AsaasProvider (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def test_factory_no_credential_returns_asaas_provider():
    """Sem credential PAGSEGURO → AsaasProvider (fallback global)."""
    from app.modules.payments.providers.asaas import AsaasProvider

    db = _make_db()
    company_id = uuid.uuid4()

    with patch(
        "app.modules.payments.providers.asaas._resolve_api_key",
        return_value="asaas_key",
    ):
        from app.modules.payments.provider_factory import get_payment_provider
        provider = get_payment_provider(company_id=company_id, db=db)

    assert isinstance(provider, AsaasProvider)


# ─────────────────────────────────────────────────────────────────────────────
# 14. Migration ORM: SAEnum aceita 'PAGSEGURO'
# ─────────────────────────────────────────────────────────────────────────────

def test_integration_credential_orm_accepts_pagseguro():
    """SAEnum credentialprovider inclui 'PAGSEGURO' como valor válido."""
    from app.infrastructure.db.models.integration_credential import IntegrationCredential

    col = IntegrationCredential.__table__.columns["provider"]
    enum_values = list(col.type.enums)

    assert "PAGSEGURO" in enum_values, (
        f"'PAGSEGURO' ausente no SAEnum. Valores presentes: {enum_values}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 15. create_charge() não usa PIX/boleto — payment_method MAQUININHA → CREDIT
# ─────────────────────────────────────────────────────────────────────────────

def test_create_charge_maquininha_maps_to_credit_not_pix():
    """payment_method='MAQUININHA' → type='CREDIT' no payload (não PIX nem BOLETO)."""
    provider = _make_pagseguro_provider()
    captured = {}

    def fake_post(path, body):
        captured.update(body)
        return _terminal_charge_response()

    with patch.object(provider, "_post", side_effect=fake_post):
        result = provider.create_charge(
            amount=Decimal("30.00"),
            customer={},
            payment_method="MAQUININHA",
            terminal_id="TERM_Y",
        )

    payment_type = captured["charges"][0]["payment_method"]["type"]
    assert payment_type == "CREDIT", f"tipo indevido: {payment_type}"
    assert payment_type not in ("PIX", "BOLETO", "DEBIT_CARD", "CREDIT_CARD"), (
        "payment_method de terminal deve ser CREDIT/DEBIT, não os tipos da API online"
    )
    assert result["payment_type"] == "CREDIT"
