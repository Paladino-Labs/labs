"""Integração Asaas — validação de create_charge, confirm() e webhook.

Casos cobertos:
  1.  create_payment(provider="asaas", method="PIX") → external_charge_id preenchido
  2.  create_payment(provider="manual", method="CASH") → external_charge_id None
  3.  confirm() com payload {"payment": {"value": 100, "fee": 3}} → amount=100, fee=3
  4.  confirm() com payload {"value": 100, "fee": 3} (legado/fallback) → amount=100, fee=3
  5.  Webhook transaction com external_charge_id inexistente → skipped: payment_not_found
  6.  [sandbox] create_subaccount() — skip se ASAAS_API_KEY ausente
  7.  [sandbox] create_charge PIX retorna external_charge_id com formato pay_xxx
  8.  [sandbox] get_status() retorna status válido para charge criada
  9.  handle_webhook() normaliza payload real Asaas (unit, sem sandbox)
  10. [sandbox] fluxo completo — curl/instruções para teste manual
  11. create_subaccount com todos os campos → payload correto montado
  12. create_subaccount com campos vazios → apenas name/email/companyType no payload
  13. create_subaccount com income_value=None → incomeValue ausente do payload
  14. update_company com novos campos → CompanyUpdate aceita os 6 novos campos
"""
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_payment(
    payment_id=None,
    company_id=None,
    status="PENDING",
    payment_method="PIX",
    provider="asaas",
    net_charged_amount=Decimal("100.00"),
    provider_fee=Decimal("0.00"),
    target_account_id=None,
    external_charge_id=None,
):
    p = MagicMock()
    p.payment_id = payment_id or uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.customer_id = uuid.uuid4()
    p.status = status
    p.payment_method = payment_method
    p.provider = provider
    p.net_charged_amount = Decimal(str(net_charged_amount))
    p.provider_fee = Decimal(str(provider_fee))
    p.target_account_id = target_account_id or uuid.uuid4()
    p.external_charge_id = external_charge_id
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
# 1. create_payment(provider="asaas", method="PIX") → external_charge_id preenchido
# ─────────────────────────────────────────────────────────────────────────────

def test_create_payment_asaas_pix_sets_external_charge_id():
    """create_payment com provider=asaas e method=PIX deve preencher external_charge_id."""
    company_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    account_id = uuid.uuid4()
    db = _make_db()

    real_payment = _make_payment(
        company_id=company_id,
        payment_method="PIX",
        provider="asaas",
        target_account_id=account_id,
    )
    db.refresh.side_effect = lambda obj: None

    mock_provider = MagicMock()
    mock_provider.create_charge.return_value = {"id": "pay_abc123", "status": "PENDING"}

    with (
        patch("app.modules.payments.service.Payment") as MockPayment,
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
    ):
        MockPayment.return_value = real_payment

        from app.modules.payments.service import create_payment

        result = create_payment(
            company_id=company_id,
            customer_id=customer_id,
            gross_amount=Decimal("100.00"),
            payment_method="PIX",
            provider="asaas",
            target_account_id=account_id,
            db=db,
        )

    mock_provider.create_charge.assert_called_once()
    call_kw = mock_provider.create_charge.call_args
    assert call_kw.kwargs["payment_method"] == "PIX"
    assert float(call_kw.kwargs["amount"]) == 100.0

    assert result.external_charge_id == "pay_abc123"
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 2. create_payment(provider="manual", method="CASH") → external_charge_id None
# ─────────────────────────────────────────────────────────────────────────────

def test_create_payment_cash_manual_no_external_charge_id():
    """create_payment com provider=manual e method=CASH não deve chamar create_charge."""
    company_id = uuid.uuid4()
    account_id = uuid.uuid4()
    db = _make_db()

    cash_payment = _make_payment(
        company_id=company_id,
        payment_method="CASH",
        provider="manual",
        target_account_id=account_id,
        external_charge_id=None,
    )
    db.refresh.side_effect = lambda obj: None

    mock_provider = MagicMock()

    with (
        patch("app.modules.payments.service.Payment") as MockPayment,
        patch("app.modules.payments.service.get_payment_provider", return_value=mock_provider),
    ):
        MockPayment.return_value = cash_payment

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

    mock_provider.create_charge.assert_not_called()
    assert result.external_charge_id is None
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 3. confirm() com payload {"payment": {"value": 100, "fee": 3}} → amount=100, fee=3
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_reads_value_and_fee_from_payment_sub_object():
    """confirm() deve ler value/fee de webhook_data['payment'] quando presente."""
    payment = _make_payment(status="PENDING", payment_method="PIX", provider="asaas")
    db = _make_db()

    captured = {}

    def capture_handle_confirmed(**kwargs):
        captured.update(kwargs)
        return {}

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus"),
    ):
        MockTxn.return_value = MagicMock()
        mock_fc.handle_payment_confirmed.side_effect = capture_handle_confirmed

        from app.modules.payments.service import confirm

        confirm(
            payment_id=payment.payment_id,
            event_id="evt_nested",
            webhook_data={
                "event": "PAYMENT_RECEIVED",
                "payment": {"id": "pay_xxx", "value": 100.0, "fee": 3.0, "status": "RECEIVED"},
            },
            company_id=payment.company_id,
            db=db,
        )

    mock_fc.handle_payment_confirmed.assert_called_once()
    assert captured["gross_amount"] == Decimal("100.00")
    # fee atualizado no payment mock via setattr — verificar via PaymentTransaction
    # O provider_fee atualizado está em payment.provider_fee (setattr no mock)
    assert payment.provider_fee == Decimal("3.0")


# ─────────────────────────────────────────────────────────────────────────────
# 4. confirm() com payload {"value": 100, "fee": 3} (legado) → amount=100, fee=3
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_fallback_reads_value_and_fee_from_root():
    """confirm() deve usar value/fee do nível raiz quando 'payment' está ausente."""
    payment = _make_payment(status="PENDING", payment_method="PIX", provider="asaas")
    db = _make_db()

    captured = {}

    def capture_handle_confirmed(**kwargs):
        captured.update(kwargs)
        return {}

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.PaymentTransaction") as MockTxn,
        patch("app.modules.payments.service.financial_core") as mock_fc,
        patch("app.modules.payments.service.mark_processed"),
        patch("app.modules.payments.service.event_bus"),
    ):
        MockTxn.return_value = MagicMock()
        mock_fc.handle_payment_confirmed.side_effect = capture_handle_confirmed

        from app.modules.payments.service import confirm

        confirm(
            payment_id=payment.payment_id,
            event_id="evt_root",
            webhook_data={"value": 100, "fee": 3},
            company_id=payment.company_id,
            db=db,
        )

    mock_fc.handle_payment_confirmed.assert_called_once()
    assert captured["gross_amount"] == Decimal("100")
    assert payment.provider_fee == Decimal("3")


# ─────────────────────────────────────────────────────────────────────────────
# 5. Webhook transaction com external_charge_id inexistente → skipped
# ─────────────────────────────────────────────────────────────────────────────

def test_webhook_transaction_skips_when_payment_not_found():
    """Webhook com external_charge_id desconhecido deve retornar skipped: payment_not_found."""
    from app.modules.payments.router import webhook_asaas_transaction

    payload = {
        "id": "evt_unknown_123",
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_nonexistent_xyz",
            "value": 100.0,
            "fee": 3.0,
            "status": "RECEIVED",
        },
    }

    # db mock que nunca encontra nenhum Payment
    db = _make_db()

    result = webhook_asaas_transaction(payload=payload, db=db)

    assert result["ok"] is True
    assert result["skipped"] == "payment_not_found"


# ─────────────────────────────────────────────────────────────────────────────
# 6. [sandbox] create_subaccount() com credencial real
# ─────────────────────────────────────────────────────────────────────────────

_SANDBOX_SKIP = pytest.mark.skipif(
    not os.environ.get("ASAAS_API_KEY"),
    reason="ASAAS_API_KEY não definida — teste sandbox ignorado",
)


@_SANDBOX_SKIP
@pytest.mark.xfail(
    strict=False,
    reason="CPF sandbox pode já estar registrado; comportamento esperado em ambiente compartilhado.",
)
def test_sandbox_create_subaccount():
    """[sandbox] create_subaccount() com todos os campos → deve retornar accountId."""
    from app.modules.payments.providers.asaas import AsaasProvider
    from app.core.config import settings

    _SANDBOX_CPF = "24971563792"

    with patch(
        "app.modules.payments.providers.asaas._resolve_api_key",
        return_value=settings.ASAAS_API_KEY,
    ):
        provider = AsaasProvider.__new__(AsaasProvider)
        provider._api_key = settings.ASAAS_API_KEY
        provider._base_url = settings.ASAAS_API_URL.rstrip("/")

    result = provider.create_subaccount(
        name="Empresa Teste Sandbox",
        cpf_cnpj=_SANDBOX_CPF,
        email="sandbox_test@paladino.app",
        birth_date="1990-01-15",
        mobile_phone="5562999990000",
        income_value=5000.00,
        address="Rua das Flores",
        address_number="123",
        province="Setor Central",
        postal_code="74000000",
    )

    assert result.get("accountId"), f"accountId vazio: {result}"
    assert "status" in result


# ─────────────────────────────────────────────────────────────────────────────
# Helpers sandbox — instancia AsaasProvider sem chamar __init__ (evita DB + RLS)
# ─────────────────────────────────────────────────────────────────────────────

def _make_sandbox_provider():
    """Retorna AsaasProvider configurado com credencial sandbox real."""
    from app.modules.payments.providers.asaas import AsaasProvider

    api_key = os.environ["ASAAS_API_KEY"]
    base_url = os.environ.get("ASAAS_API_URL", "https://sandbox.asaas.com/api/v3").rstrip("/")

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._api_key = api_key
    provider._base_url = base_url
    return provider


def _get_or_create_sandbox_customer(provider) -> str:
    """Retorna o ID de um customer Asaas sandbox, criando-o se necessário.

    Usa CPF 24971563792 (válido para sandbox). Reutiliza o customer se
    já existir na conta — evita duplicatas entre rodadas de teste.
    """
    from app.modules.payments.providers.asaas import AsaasError

    CPF = "24971563792"
    # Tenta encontrar customer já existente
    search = provider._get(f"/customers?cpfCnpj={CPF}&limit=1")
    existing = search.get("data", [])
    if existing:
        return existing[0]["id"]

    # Cria se não existir (email único por rodada evita conflito de e-mail)
    new_cust = provider._post("/customers", {
        "name": "Teste QA Paladino",
        "email": f"qa_{uuid.uuid4().hex[:8]}@paladino.test",
        "cpfCnpj": CPF,
    })
    return new_cust["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 7. [sandbox] create_charge PIX → external_charge_id com formato pay_xxx
# ─────────────────────────────────────────────────────────────────────────────

@_SANDBOX_SKIP
def test_real_asaas_create_charge_pix():
    """[sandbox] Cria cobrança PIX real no Asaas sandbox.

    Verifica:
    - external_charge_id retornado com formato pay_xxx
    - status é PENDING ou ACTIVE
    - value reflete o montante enviado
    """
    provider = _make_sandbox_provider()
    customer_id = _get_or_create_sandbox_customer(provider)

    result = provider.create_charge(
        amount=Decimal("10.00"),
        customer={"external_id": customer_id},
        payment_method="PIX",
        dueDate=(date.today() + timedelta(days=1)).isoformat(),
    )

    charge_id = result.get("id", "")
    print(f"\nexternal_charge_id criado: {charge_id}")
    print(f"Status: {result.get('status')}")
    print(f"Valor: {result.get('value')}")
    print(f"billingType: {result.get('billingType')}")

    assert charge_id, f"id ausente no response: {result}"
    assert charge_id.startswith("pay_"), f"ID inesperado (esperado pay_xxx): {charge_id}"
    assert result.get("status") in ("PENDING", "ACTIVE"), \
        f"Status inesperado: {result.get('status')}"
    assert float(result.get("value", 0)) == 10.0, \
        f"Valor divergente: {result.get('value')}"
    assert result.get("billingType") == "PIX", \
        f"billingType inesperado: {result.get('billingType')}"


# ─────────────────────────────────────────────────────────────────────────────
# 8. [sandbox] get_status retorna status válido para charge criada
# ─────────────────────────────────────────────────────────────────────────────

_VALID_CHARGE_STATUSES = {"PENDING", "ACTIVE", "RECEIVED", "CONFIRMED", "OVERDUE"}


@_SANDBOX_SKIP
def test_real_asaas_get_status():
    """[sandbox] Cria charge PIX e imediatamente consulta get_status().

    Verifica que:
    - get_status() retorna string (não levanta exceção)
    - status está no conjunto de valores válidos do Asaas
    """
    provider = _make_sandbox_provider()
    customer_id = _get_or_create_sandbox_customer(provider)

    charge = provider.create_charge(
        amount=Decimal("10.00"),
        customer={"external_id": customer_id},
        payment_method="PIX",
        dueDate=(date.today() + timedelta(days=1)).isoformat(),
    )
    charge_id = charge["id"]

    status = provider.get_status(charge_id)

    print(f"\nget_status({charge_id}) = {status}")

    assert isinstance(status, str), f"get_status deve retornar str, obteve: {type(status)}"
    assert status in _VALID_CHARGE_STATUSES, \
        f"Status inválido: {status!r}. Esperado: {_VALID_CHARGE_STATUSES}"


# ─────────────────────────────────────────────────────────────────────────────
# 9. handle_webhook() normaliza payload real do Asaas (unit — sem sandbox)
# ─────────────────────────────────────────────────────────────────────────────

def test_handle_webhook_real_payload_structure():
    """handle_webhook() normaliza o payload EXATO enviado pelo Asaas.

    Nota: handle_webhook NÃO extrai value/fee — esse parse acontece em
    confirm() (testado em test_confirm_reads_value_and_fee_from_payment_sub_object).
    Este teste verifica apenas o parse de external_id, status e event.
    """
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._api_key = "dummy"
    provider._base_url = "https://sandbox.asaas.com/api/v3"

    real_asaas_payload = {
        "event": "PAYMENT_RECEIVED",
        "payment": {
            "id": "pay_sandbox_test_001",
            "dateCreated": "2026-06-02",
            "customer": "cus_000008076728",
            "value": 100.00,
            "netValue": 97.00,
            "fee": 3.00,
            "status": "RECEIVED",
            "paymentDate": "2026-06-02",
            "billingType": "PIX",
        },
    }

    result = provider.handle_webhook(real_asaas_payload)

    print(f"\nhandle_webhook result: {result}")

    assert result["event"] == "PAYMENT_RECEIVED"
    assert result["external_id"] == "pay_sandbox_test_001", \
        f"external_id incorreto: {result['external_id']}"
    assert result["status"] == "RECEIVED", \
        f"status incorreto: {result['status']}"
    assert result["raw"] is real_asaas_payload, \
        "raw deve ser o payload original (sem cópia)"

    # value e fee NÃO estão no resultado de handle_webhook — são lidos
    # em confirm() via webhook_data["payment"]["value/fee"].
    # Ver: test_confirm_reads_value_and_fee_from_payment_sub_object
    assert "value" not in result, \
        "handle_webhook não deve expor 'value' diretamente (isso é papel do confirm)"


# ─────────────────────────────────────────────────────────────────────────────
# 11. create_subaccount com todos os campos → payload correto montado
# ─────────────────────────────────────────────────────────────────────────────

def test_create_subaccount_full_payload():
    """create_subaccount com todos os campos envia o payload completo ao Asaas."""
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._api_key = "dummy"
    provider._base_url = "https://sandbox.asaas.com/api/v3"

    captured_payload = {}

    def fake_post(path, body):
        captured_payload.update(body)
        return {"id": "acc_test123", "accountStatus": "pending_verification"}

    provider._post = fake_post

    result = provider.create_subaccount(
        name="Barbearia Teste",
        cpf_cnpj="24971563792",
        email="owner@barbearia.com",
        birth_date="1985-06-15",
        mobile_phone="5562988887777",
        income_value=8000.00,
        address="Rua das Acácias",
        address_number="42",
        province="Jardim América",
        postal_code="74110120",
    )

    assert captured_payload["name"] == "Barbearia Teste"
    assert captured_payload["email"] == "owner@barbearia.com"
    assert captured_payload["companyType"] == "MEI"
    assert captured_payload["cpfCnpj"] == "24971563792"
    assert captured_payload["birthDate"] == "1985-06-15"
    assert captured_payload["mobilePhone"] == "5562988887777"
    assert captured_payload["incomeValue"] == 8000.00
    assert captured_payload["address"] == "Rua das Acácias"
    assert captured_payload["addressNumber"] == "42"
    assert captured_payload["province"] == "Jardim América"
    assert captured_payload["postalCode"] == "74110120"
    assert result["accountId"] == "acc_test123"
    assert result["status"] == "pending_verification"


# ─────────────────────────────────────────────────────────────────────────────
# 12. create_subaccount com campos vazios → apenas name/email/companyType
# ─────────────────────────────────────────────────────────────────────────────

def test_create_subaccount_empty_fields_omitted():
    """Campos vazios ou None não devem aparecer no payload enviado ao Asaas."""
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._api_key = "dummy"
    provider._base_url = "https://sandbox.asaas.com/api/v3"

    captured_payload = {}

    def fake_post(path, body):
        captured_payload.update(body)
        return {"id": "acc_min123", "accountStatus": "pending_verification"}

    provider._post = fake_post

    provider.create_subaccount(
        name="Empresa Mínima",
        cpf_cnpj="",
        email="minimal@example.com",
    )

    assert set(captured_payload.keys()) == {"name", "email", "companyType"}
    assert "cpfCnpj" not in captured_payload
    assert "birthDate" not in captured_payload
    assert "mobilePhone" not in captured_payload
    assert "incomeValue" not in captured_payload
    assert "address" not in captured_payload
    assert "addressNumber" not in captured_payload
    assert "province" not in captured_payload
    assert "postalCode" not in captured_payload


# ─────────────────────────────────────────────────────────────────────────────
# 13. create_subaccount com income_value=None → incomeValue ausente do payload
# ─────────────────────────────────────────────────────────────────────────────

def test_create_subaccount_income_value_none_omitted():
    """income_value=None não deve incluir incomeValue no payload."""
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._api_key = "dummy"
    provider._base_url = "https://sandbox.asaas.com/api/v3"

    captured_payload = {}

    def fake_post(path, body):
        captured_payload.update(body)
        return {"id": "acc_no_income", "accountStatus": "pending_verification"}

    provider._post = fake_post

    provider.create_subaccount(
        name="Sem Renda",
        cpf_cnpj="24971563792",
        email="sem_renda@example.com",
        mobile_phone="5562911112222",
        income_value=None,
        address="Rua Teste",
        address_number="1",
        province="Centro",
        postal_code="74000001",
    )

    assert "incomeValue" not in captured_payload
    assert captured_payload.get("mobilePhone") == "5562911112222"
    assert captured_payload.get("address") == "Rua Teste"


# ─────────────────────────────────────────────────────────────────────────────
# 14. CompanyUpdate aceita os 6 novos campos
# ─────────────────────────────────────────────────────────────────────────────

def test_company_update_schema_accepts_new_fields():
    """CompanyUpdate deve aceitar e expor os 6 novos campos owner_*."""
    from app.modules.companies.schemas import CompanyUpdate

    data = CompanyUpdate(
        owner_mobile_phone="5562999990000",
        owner_income_value=5000.0,
        owner_address="Rua das Flores",
        owner_address_number="123",
        owner_province="Setor Central",
        owner_postal_code="74000000",
    )

    dumped = data.model_dump(exclude_none=True)
    assert dumped["owner_mobile_phone"] == "5562999990000"
    assert dumped["owner_income_value"] == 5000.0
    assert dumped["owner_address"] == "Rua das Flores"
    assert dumped["owner_address_number"] == "123"
    assert dumped["owner_province"] == "Setor Central"
    assert dumped["owner_postal_code"] == "74000000"
    # Campos de nome/slug não enviados → não presentes no dump
    assert "name" not in dumped
    assert "slug" not in dumped


# ─────────────────────────────────────────────────────────────────────────────
# 10. [sandbox] Fluxo completo — instruções de teste manual
# ─────────────────────────────────────────────────────────────────────────────
#
# O fluxo completo (create_payment → webhook → confirm → CONFIRMED) requer
# um banco PostgreSQL real com todas as migrations aplicadas + RLS configurado.
# Automatizar esse setup em testes unitários seria inviável sem um ambiente
# de staging dedicado.
#
# TESTE MANUAL — execute após rodar o servidor local ou apontar para staging:
#
# ── Passo 1: criar pagamento PIX ───────────────────────────────────────────
# curl -s -X POST http://localhost:8000/payments \
#   -H "Authorization: Bearer <TOKEN_OWNER>" \
#   -H "Content-Type: application/json" \
#   -d '{
#     "gross_amount": "10.00",
#     "payment_method": "PIX",
#     "provider": "asaas",
#     "target_account_id": "<UUID_CONTA_CAIXA>",
#     "customer_id": "<UUID_CUSTOMER>"
#   }' | jq '{payment_id, external_charge_id, status}'
#
# Resposta esperada:
#   { "payment_id": "...", "external_charge_id": "pay_xxx", "status": "PENDING" }
#
# ── Passo 2: simular pagamento no Asaas sandbox ────────────────────────────
# 1. Acesse https://sandbox.asaas.com
# 2. Vá em Cobranças → localize a cobrança pelo ID retornado acima
# 3. Clique em "Simular pagamento" → PIX → Confirmar
#
# ── Passo 3: verificar que o webhook chegou e o Payment ficou CONFIRMED ────
# curl -s http://localhost:8000/payments/<PAYMENT_ID> \
#   -H "Authorization: Bearer <TOKEN_OWNER>" | jq '{status, paid_at, provider_fee}'
#
# Resposta esperada:
#   { "status": "CONFIRMED", "paid_at": "2026-...", "provider_fee": "0.21" }
#
# ── Alternativa: simular webhook manualmente ───────────────────────────────
# curl -s -X POST http://localhost:8000/payments/webhook/asaas/transaction \
#   -H "Content-Type: application/json" \
#   -d '{
#     "id": "evt_manual_001",
#     "event": "PAYMENT_RECEIVED",
#     "payment": {
#       "id": "pay_xxx",
#       "value": 10.00,
#       "netValue": 9.79,
#       "fee": 0.21,
#       "status": "RECEIVED",
#       "paymentDate": "2026-06-02"
#     }
#   }' | jq .
#
# ──────────────────────────────────────────────────────────────────────────
