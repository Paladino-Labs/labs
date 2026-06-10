"""Testes do endpoint e serviço de políticas de taxa MDR (fee-policies).

Casos cobertos:
  1.  list_fee_routing_policies → retorna lista com 10 políticas (inclui CHAVE_PIX e bandeiras)
  2.  update_fee_policy_calculation → atualiza fee_percentage e retorna policy
  3.  FeePolicyUpdate rejeita fee_percentage > 100.0 (ValidationError Pydantic)
  4.  update_fee_policy_calculation → 404 para fee_source desconhecido
  5.  confirm_manual usa o percentual atualizado via política
  6.  PATCH /financial/fee-policies/MAQUININHA_PIX → atualiza percentual
  7.  Após PATCH, confirm_manual MAQUININHA_PIX usa novo percentual (sem warning)

Abordagem: unit tests com mocks (sem PostgreSQL real).
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_db():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.refresh = MagicMock()
    return db


def _make_policy(
    fee_source="MAQUININHA_CREDIT_OUTROS",
    fee_percentage=Decimal("0"),
    fee_flat=Decimal("0"),
    is_active=True,
    company_id=None,
):
    p = MagicMock()
    p.policy_id = uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.fee_source = fee_source
    # fee_percentage=None = "não configurado" (dispara fee_warning)
    p.fee_percentage = None if fee_percentage is None else Decimal(str(fee_percentage))
    p.fee_flat = Decimal(str(fee_flat))
    p.is_active = is_active
    p.client_share = Decimal("0")
    p.tenant_share = Decimal("100")
    p.professional_share = Decimal("0")
    return p


FEE_SOURCES_10 = [
    "CASH", "CHAVE_PIX", "MAQUININHA_PIX",
    "MAQUININHA_CREDIT_VISA_MASTER", "MAQUININHA_CREDIT_ELO",
    "MAQUININHA_CREDIT_HIPER_AMEX", "MAQUININHA_CREDIT_OUTROS",
    "MAQUININHA_DEBIT_VISA_MASTER", "MAQUININHA_DEBIT_ELO",
    "MAQUININHA_DEBIT_OUTROS",
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. list_fee_routing_policies → retorna lista com 10 políticas (inclui CHAVE_PIX)
# ─────────────────────────────────────────────────────────────────────────────

def test_list_fee_policies_returns_ten_policies():
    """list_fee_routing_policies deve retornar as 10 políticas do tenant (incluindo CHAVE_PIX e bandeiras)."""
    company_id = uuid.uuid4()
    policies = [_make_policy(fee_source=fs, company_id=company_id) for fs in FEE_SOURCES_10]
    db = _make_db()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = policies

    from app.modules.financial_core.service import list_fee_routing_policies

    result = list_fee_routing_policies(company_id=company_id, db=db)

    assert len(result) == 10
    returned_sources = {p.fee_source for p in result}
    assert returned_sources == set(FEE_SOURCES_10)
    assert "CHAVE_PIX" in returned_sources
    assert "MAQUININHA_CREDIT_VISA_MASTER" in returned_sources


# ─────────────────────────────────────────────────────────────────────────────
# 2. update_fee_policy_calculation → atualiza fee_percentage
# ─────────────────────────────────────────────────────────────────────────────

def test_update_fee_policy_updates_percentage():
    """update_fee_policy_calculation deve persistir novo fee_percentage."""
    company_id = uuid.uuid4()
    policy = _make_policy(
        fee_source="MAQUININHA_CREDIT_OUTROS",
        fee_percentage=Decimal("0"),
        company_id=company_id,
    )
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = policy

    from app.modules.financial_core.service import update_fee_policy_calculation

    result = update_fee_policy_calculation(
        fee_source="MAQUININHA_CREDIT_OUTROS",
        company_id=company_id,
        db=db,
        fee_percentage=Decimal("3.99"),
    )

    assert policy.fee_percentage == Decimal("3.99")
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(policy)


# ─────────────────────────────────────────────────────────────────────────────
# 3. FeePolicyUpdate rejeita fee_percentage > 100.0
# ─────────────────────────────────────────────────────────────────────────────

def test_fee_policy_update_schema_rejects_out_of_range():
    """FeePolicyUpdate deve rejeitar fee_percentage > 100.0 via Pydantic."""
    from app.modules.financial_core.schemas import FeePolicyUpdate

    with pytest.raises(ValidationError):
        FeePolicyUpdate(fee_percentage=Decimal("150.0"))


def test_fee_policy_update_schema_accepts_valid_percentage():
    """FeePolicyUpdate deve aceitar fee_percentage dentro do range [0, 100]."""
    from app.modules.financial_core.schemas import FeePolicyUpdate

    schema = FeePolicyUpdate(fee_percentage=Decimal("3.99"))
    assert schema.fee_percentage == Decimal("3.99")


# ─────────────────────────────────────────────────────────────────────────────
# 4. update_fee_policy_calculation → 404 para fee_source desconhecido
# ─────────────────────────────────────────────────────────────────────────────

def test_update_fee_policy_404_for_unknown_fee_source():
    """update_fee_policy_calculation deve levantar HTTP 404 para fee_source inexistente."""
    from fastapi import HTTPException

    company_id = uuid.uuid4()
    db = _make_db()
    # first() retorna None → get_fee_routing_policy_or_404 levanta 404
    db.query.return_value.filter.return_value.first.return_value = None

    from app.modules.financial_core.service import update_fee_policy_calculation

    with pytest.raises(HTTPException) as exc_info:
        update_fee_policy_calculation(
            fee_source="FEE_SOURCE_INEXISTENTE",
            company_id=company_id,
            db=db,
            fee_percentage=Decimal("5.0"),
        )

    assert exc_info.value.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# 5. confirm_manual usa fee_percentage atualizado
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_uses_updated_fee_percentage():
    """Após atualizar política para 5.0%, confirm_manual calcula fee correto."""
    gross = Decimal("100.00")
    company_id = uuid.uuid4()

    # Simula policy com 5.0% atualizado
    policy = _make_policy(
        fee_source="MAQUININHA_CREDIT_OUTROS",
        fee_percentage=Decimal("5.0"),
        company_id=company_id,
    )

    payment = MagicMock()
    payment.payment_id = uuid.uuid4()
    payment.company_id = company_id
    payment.status = "PENDING"
    payment.payment_method = "MAQUININHA"
    payment.provider = "manual"
    payment.net_charged_amount = gross
    payment.gross_catalog_amount = gross
    payment._sa_instance_state = MagicMock()
    payment._sa_instance_state.has_identity = False

    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        _confirmed, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=company_id,
            db=db,
        )

    # fee = 100.00 * 5.0 / 100 = 5.00
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "5.00"
    assert fee_warning is None  # política configurada → sem aviso


# ─────────────────────────────────────────────────────────────────────────────
# 6. PATCH /financial/fee-policies/MAQUININHA_PIX → atualiza percentual
# ─────────────────────────────────────────────────────────────────────────────

def test_update_maquininha_pix_policy():
    """update_fee_policy_calculation deve atualizar MAQUININHA_PIX de NULL para 0.99."""
    company_id = uuid.uuid4()
    policy = _make_policy(
        fee_source="MAQUININHA_PIX",
        fee_percentage=None,   # inicia não configurado
        company_id=company_id,
    )
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = policy

    from app.modules.financial_core.service import update_fee_policy_calculation

    update_fee_policy_calculation(
        fee_source="MAQUININHA_PIX",
        company_id=company_id,
        db=db,
        fee_percentage=Decimal("0.99"),
    )

    assert policy.fee_percentage == Decimal("0.99")
    db.commit.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# 7. Após PATCH MAQUININHA_PIX, confirm_manual usa novo percentual (sem warning)
# ─────────────────────────────────────────────────────────────────────────────

def test_confirm_manual_maquininha_pix_after_patch_no_warning():
    """Após configurar MAQUININHA_PIX com 0.99%, confirm_manual calcula fee e não avisa."""
    gross = Decimal("100.00")
    company_id = uuid.uuid4()

    # Política com fee_percentage configurado (após PATCH)
    policy = _make_policy(
        fee_source="MAQUININHA_PIX",
        fee_percentage=Decimal("0.99"),
        company_id=company_id,
    )

    payment = MagicMock()
    payment.payment_id = uuid.uuid4()
    payment.company_id = company_id
    payment.status = "PENDING"
    payment.payment_method = "MAQUININHA_PIX"
    payment.provider = "manual"
    payment.net_charged_amount = gross
    payment.gross_catalog_amount = gross
    payment._sa_instance_state = MagicMock()
    payment._sa_instance_state.has_identity = False

    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = policy

    with (
        patch("app.modules.payments.service._get_payment", return_value=payment),
        patch("app.modules.payments.service.is_processed", return_value=False),
        patch("app.modules.payments.service.confirm", return_value=payment) as mock_confirm,
    ):
        from app.modules.payments.service import confirm_manual

        _confirmed, fee_warning = confirm_manual(
            payment_id=payment.payment_id,
            company_id=company_id,
            db=db,
        )

    # fee = 100.00 * 0.99 / 100 = 0.99
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "0.99"
    assert fee_warning is None  # taxa configurada → sem aviso
