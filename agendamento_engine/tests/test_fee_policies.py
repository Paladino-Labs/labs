"""Testes do endpoint e serviço de políticas de taxa MDR (fee-policies).

Casos cobertos:
  1.  list_fee_routing_policies → retorna lista com 7 políticas
  2.  update_fee_policy_calculation → atualiza fee_percentage e retorna policy
  3.  FeePolicyUpdate rejeita fee_percentage > 100.0 (ValidationError Pydantic)
  4.  update_fee_policy_calculation → 404 para fee_source desconhecido
  5.  confirm_manual usa o percentual atualizado via política

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
    fee_source="MAQUININHA_CREDIT",
    fee_percentage=Decimal("0"),
    fee_flat=Decimal("0"),
    is_active=True,
    company_id=None,
):
    p = MagicMock()
    p.policy_id = uuid.uuid4()
    p.company_id = company_id or uuid.uuid4()
    p.fee_source = fee_source
    p.fee_percentage = Decimal(str(fee_percentage))
    p.fee_flat = Decimal(str(fee_flat))
    p.is_active = is_active
    p.client_share = Decimal("0")
    p.tenant_share = Decimal("100")
    p.professional_share = Decimal("0")
    return p


FEE_SOURCES_7 = [
    "ASAAS_PIX", "ASAAS_CARD", "MAQUININHA_CREDIT", "MAQUININHA_DEBIT",
    "ANTECIPACAO", "ESTORNO", "RECORRENTE_FEE",
]


# ─────────────────────────────────────────────────────────────────────────────
# 1. list_fee_routing_policies → retorna lista com 7 políticas
# ─────────────────────────────────────────────────────────────────────────────

def test_list_fee_policies_returns_seven_policies():
    """list_fee_routing_policies deve retornar as 7 políticas do tenant."""
    company_id = uuid.uuid4()
    policies = [_make_policy(fee_source=fs, company_id=company_id) for fs in FEE_SOURCES_7]
    db = _make_db()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = policies

    from app.modules.financial_core.service import list_fee_routing_policies

    result = list_fee_routing_policies(company_id=company_id, db=db)

    assert len(result) == 7
    returned_sources = {p.fee_source for p in result}
    assert returned_sources == set(FEE_SOURCES_7)


# ─────────────────────────────────────────────────────────────────────────────
# 2. update_fee_policy_calculation → atualiza fee_percentage
# ─────────────────────────────────────────────────────────────────────────────

def test_update_fee_policy_updates_percentage():
    """update_fee_policy_calculation deve persistir novo fee_percentage."""
    company_id = uuid.uuid4()
    policy = _make_policy(
        fee_source="MAQUININHA_CREDIT",
        fee_percentage=Decimal("0"),
        company_id=company_id,
    )
    db = _make_db()
    db.query.return_value.filter.return_value.first.return_value = policy

    from app.modules.financial_core.service import update_fee_policy_calculation

    result = update_fee_policy_calculation(
        fee_source="MAQUININHA_CREDIT",
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
        fee_source="MAQUININHA_CREDIT",
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

        confirm_manual(
            payment_id=payment.payment_id,
            company_id=company_id,
            db=db,
        )

    # fee = 100.00 * 5.0 / 100 = 5.00
    call_kwargs = mock_confirm.call_args.kwargs
    assert call_kwargs["webhook_data"]["fee"] == "5.00"
