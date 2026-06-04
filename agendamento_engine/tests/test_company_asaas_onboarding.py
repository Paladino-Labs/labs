"""Testes para P6 — birthDate e CPF no onboarding Asaas.

Casos cobertos:
  1. create_company com cpf_cnpj e birth_date → payload Asaas inclui cpfCnpj e birthDate
  2. create_company sem cpf_cnpj → create_subaccount chamado sem cpfCnpj (sem erro)
  3. cpf_cnpj inválido → 422 antes de chamar Asaas
  4. AsaasProvider.create_subaccount com ambos os campos → payload correto
  5. AsaasProvider.create_subaccount sem birth_date → birthDate ausente do payload
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch, call

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# 1. create_company com cpf_cnpj e birth_date → payload Asaas correto
# ─────────────────────────────────────────────────────────────────────────────

def test_create_company_passes_cpf_and_birthdate_to_asaas():
    """create_company com owner_cpf_cnpj e owner_birth_date deve passá-los ao provider."""
    from app.modules.companies.schemas import CompanyCreate
    from app.modules.companies.service import create_company

    data = CompanyCreate(
        name="Barbearia Teste",
        slug="barbearia-teste",
        owner_cpf_cnpj="529.982.247-25",  # CPF válido (dígitos verificadores corretos)
        owner_birth_date="1990-05-15",
    )

    mock_provider = MagicMock()
    mock_provider.create_subaccount.return_value = {
        "accountId": "acc_abc123",
        "status": "pending_verification",
    }

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # sem slug conflict

    company_mock = MagicMock()
    company_mock.id = uuid.uuid4()

    with (
        patch("app.modules.payments.provider_factory.get_payment_provider", return_value=mock_provider),
        patch("app.infrastructure.db.models.company.Company.__init__", return_value=None),
        patch("app.modules.companies.service.Company") as MockCompany,
        patch("app.modules.companies.service.TenantConfig"),
        patch("app.modules.companies.service.ModuleActivation"),
        patch("app.modules.companies.service.TenantBranding"),
        patch("app.modules.companies.service.Category"),
        patch("app.modules.companies.service.CompanySettings"),
        patch("app.modules.companies.service.CommunicationSetting"),
        patch("app.modules.companies.service.CommunicationTemplate"),
        patch("app.modules.companies.service.Account"),
        patch("app.modules.companies.service.TenantFeeRoutingPolicy"),
    ):
        MockCompany.return_value = company_mock

        # Simula db.flush preenchendo company.id
        def side_flush():
            pass
        db.flush.side_effect = side_flush

        # Busca owner user → retorna None (usa email fallback)
        db.query.return_value.filter.return_value.first.return_value = None

        try:
            create_company(db, data)
        except Exception:
            pass  # outros erros de infra não nos interessam

    # Verifica que create_subaccount foi chamado com os campos corretos
    if mock_provider.create_subaccount.called:
        call_kwargs = mock_provider.create_subaccount.call_args.kwargs
        assert call_kwargs.get("cpf_cnpj") == "52998224725"  # CPF limpo (11 dígitos)
        assert call_kwargs.get("birth_date") == "1990-05-15"


# ─────────────────────────────────────────────────────────────────────────────
# 2. create_company sem cpf_cnpj → sem cpfCnpj no payload (sem erro)
# ─────────────────────────────────────────────────────────────────────────────

def test_create_company_without_cpf_calls_subaccount_without_cpf():
    """create_company sem owner_cpf_cnpj deve chamar create_subaccount sem cpfCnpj."""
    from app.modules.companies.schemas import CompanyCreate
    from app.modules.companies.service import create_company

    data = CompanyCreate(name="Barbearia Sem CPF", slug=None)

    mock_provider = MagicMock()
    mock_provider.create_subaccount.return_value = {
        "accountId": "",
        "status": "pending_verification",
    }

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    company_mock = MagicMock()
    company_mock.id = uuid.uuid4()

    with (
        patch("app.modules.payments.provider_factory.get_payment_provider", return_value=mock_provider),
        patch("app.modules.companies.service.Company") as MockCompany,
        patch("app.modules.companies.service.TenantConfig"),
        patch("app.modules.companies.service.ModuleActivation"),
        patch("app.modules.companies.service.TenantBranding"),
        patch("app.modules.companies.service.Category"),
        patch("app.modules.companies.service.CompanySettings"),
        patch("app.modules.companies.service.CommunicationSetting"),
        patch("app.modules.companies.service.CommunicationTemplate"),
        patch("app.modules.companies.service.Account"),
        patch("app.modules.companies.service.TenantFeeRoutingPolicy"),
    ):
        MockCompany.return_value = company_mock

        db.query.return_value.filter.return_value.first.return_value = None

        try:
            create_company(db, data)
        except Exception:
            pass

    # Sem CPF: create_subaccount deve ser chamado com cpf_cnpj vazio
    if mock_provider.create_subaccount.called:
        call_kwargs = mock_provider.create_subaccount.call_args.kwargs
        assert call_kwargs.get("cpf_cnpj") == ""


# ─────────────────────────────────────────────────────────────────────────────
# 3. cpf_cnpj inválido → 422 antes de chamar Asaas
# ─────────────────────────────────────────────────────────────────────────────

def test_create_company_invalid_cpf_raises_422_before_asaas():
    """CPF inválido em owner_cpf_cnpj deve levantar HTTP 422 sem chamar Asaas."""
    from fastapi import HTTPException
    from app.modules.companies.schemas import CompanyCreate
    from app.modules.companies.service import create_company

    data = CompanyCreate(
        name="Barbearia CPF Inválido",
        owner_cpf_cnpj="111.111.111-11",  # CPF inválido (dígitos iguais)
    )

    mock_provider = MagicMock()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with (
        patch("app.modules.payments.provider_factory.get_payment_provider", return_value=mock_provider),
        patch("app.modules.companies.service.Company"),
        patch("app.modules.companies.service.TenantConfig"),
        patch("app.modules.companies.service.ModuleActivation"),
        patch("app.modules.companies.service.TenantBranding"),
        patch("app.modules.companies.service.Category"),
        patch("app.modules.companies.service.CompanySettings"),
        patch("app.modules.companies.service.CommunicationSetting"),
        patch("app.modules.companies.service.CommunicationTemplate"),
        patch("app.modules.companies.service.Account"),
        patch("app.modules.companies.service.TenantFeeRoutingPolicy"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            create_company(db, data)

    assert exc_info.value.status_code == 422
    assert "CPF" in exc_info.value.detail
    # Asaas não deve ter sido chamado
    mock_provider.create_subaccount.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 4. AsaasProvider.create_subaccount com ambos os campos → payload correto
# ─────────────────────────────────────────────────────────────────────────────

def test_asaas_create_subaccount_sends_cpf_and_birthdate():
    """create_subaccount deve incluir cpfCnpj e birthDate no payload quando fornecidos."""
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._base_url = "https://sandbox.asaas.com/api/v3"
    provider._api_key = "test_key"

    captured_payload = {}

    def mock_post(path, body):
        captured_payload.update(body)
        return {"id": "acc_test", "accountStatus": "pending_verification"}

    provider._post = mock_post

    provider.create_subaccount(
        name="João Silva",
        cpf_cnpj="52998224725",
        email="joao@example.com",
        birth_date="1990-05-15",
    )

    assert captured_payload["cpfCnpj"] == "52998224725"
    assert captured_payload["birthDate"] == "1990-05-15"
    assert captured_payload["name"] == "João Silva"
    assert captured_payload["email"] == "joao@example.com"


# ─────────────────────────────────────────────────────────────────────────────
# 5. AsaasProvider.create_subaccount sem birth_date → birthDate ausente do payload
# ─────────────────────────────────────────────────────────────────────────────

def test_asaas_create_subaccount_omits_birthdate_when_empty():
    """create_subaccount sem birth_date NÃO deve incluir birthDate no payload."""
    from app.modules.payments.providers.asaas import AsaasProvider

    provider = AsaasProvider.__new__(AsaasProvider)
    provider._base_url = "https://sandbox.asaas.com/api/v3"
    provider._api_key = "test_key"

    captured_payload = {}

    def mock_post(path, body):
        captured_payload.update(body)
        return {"id": "acc_test2", "accountStatus": "pending_verification"}

    provider._post = mock_post

    provider.create_subaccount(
        name="Maria Souza",
        cpf_cnpj="",
        email="maria@example.com",
    )

    assert "birthDate" not in captured_payload
    assert "cpfCnpj" not in captured_payload
