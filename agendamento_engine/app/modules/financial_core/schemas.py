"""Schemas Pydantic do módulo Financial Core."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ── TenantFeeRoutingPolicy ────────────────────────────────────────────────────

class FeeRoutingResponse(BaseModel):
    policy_id: UUID
    company_id: UUID
    fee_source: str
    client_share: Decimal
    tenant_share: Decimal
    professional_share: Decimal
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FeeRoutingUpdate(BaseModel):
    client_share: Decimal = Field(..., ge=0, le=100)
    tenant_share: Decimal = Field(..., ge=0, le=100)
    professional_share: Decimal = Field(..., ge=0, le=100)

    @model_validator(mode="after")
    def check_sum_100(self) -> "FeeRoutingUpdate":
        total = self.client_share + self.tenant_share + self.professional_share
        if total != Decimal("100"):
            raise ValueError(
                f"A soma de client_share + tenant_share + professional_share deve ser 100. "
                f"Recebido: {total}"
            )
        return self


class FeePolicyResponse(BaseModel):
    """Política de cálculo de taxa MDR por fee_source.

    Exposta em GET/PATCH /financial/fee-policies.

    fee_percentage é nullable no banco (NULL = taxa não configurada).
    fee_flat pode ser NULL em tenants migrados antes do default=0.
    """
    policy_id: UUID
    company_id: UUID
    fee_source: str
    fee_percentage: Optional[Decimal] = None
    fee_flat: Optional[Decimal] = None
    is_active: bool
    client_share: Decimal
    tenant_share: Decimal
    professional_share: Decimal
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class FeePolicyUpdate(BaseModel):
    """Atualização parcial de política de taxa MDR.

    fee_percentage: 0.0 a 100.0 (ex: 3.99 = 3,99%).
    fee_flat: valor fixo adicional por transação (>= 0).
    is_active: desativar impede cálculo de taxa neste fee_source.
    """
    fee_percentage: Optional[Decimal] = Field(None, ge=0, le=100)
    fee_flat: Optional[Decimal] = Field(None, ge=0)
    is_active: Optional[bool] = None


# ── Account ───────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    type: str = Field(..., pattern="^(CAIXA|ACQUIRER|BANK|ESCROW)$")
    provider: Optional[str] = None
    external_ref: Optional[str] = None
    currency: str = Field("BRL", min_length=3, max_length=3)
    is_default_inflow: bool = False


class AccountResponse(BaseModel):
    account_id: UUID
    company_id: UUID
    name: str
    type: str
    provider: Optional[str] = None
    external_ref: Optional[str] = None
    currency: str
    status: str
    is_default_inflow: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class BalanceResponse(BaseModel):
    account_id: UUID
    balance: Decimal
    as_of: Optional[datetime] = None


# ── Movement ─────────────────────────────────────────────────────────────────

class MovementResponse(BaseModel):
    movement_id: UUID
    company_id: UUID
    account_id: UUID
    type: str
    amount: Decimal
    occurred_at: datetime
    source_type: str
    source_id: UUID
    transfer_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class MovementFilters(BaseModel):
    account_id: Optional[UUID] = None
    type: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


# ── Entry ─────────────────────────────────────────────────────────────────────

class EntryResponse(BaseModel):
    entry_id: UUID
    company_id: UUID
    type: str
    direction: str
    amount: Decimal
    occurred_at: datetime
    category: str
    source_type: str
    source_id: UUID
    movement_id: Optional[UUID] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EntryFilters(BaseModel):
    type: Optional[str] = None
    category: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


# ── DRE ───────────────────────────────────────────────────────────────────────

class DreResponse(BaseModel):
    date_from: datetime
    date_to: datetime
    receita: dict[str, Decimal]
    receita_total: Decimal
    custo: dict[str, Decimal]
    custo_total: Decimal
    despesa: dict[str, Decimal]
    despesa_total: Decimal
    taxa: dict[str, Decimal]
    taxa_total: Decimal
    comissao: dict[str, Decimal]
    comissao_total: Decimal
    estorno: dict[str, Decimal]
    estorno_total: Decimal
    ajuste: dict[str, Decimal]
    ajuste_total: Decimal
    resultado_bruto: Decimal   # receita - custo
    resultado_liquido: Decimal  # resultado_bruto - despesa - taxa - comissao + estorno + ajuste


# ── ManualAdjustment ──────────────────────────────────────────────────────────

class ManualAdjustmentCreate(BaseModel):
    amount: Decimal = Field(..., gt=0)
    direction: str = Field(..., pattern="^(ADDS|SUBTRACTS)$")
    category: str
    account_id: UUID
    reason: str = Field(..., min_length=5, description="Motivo obrigatório para audit trail")


# ── Transfer ──────────────────────────────────────────────────────────────────

class TransferCreate(BaseModel):
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal = Field(..., gt=0)
    notes: Optional[str] = None


class TransferResponse(BaseModel):
    transfer_id: UUID
    company_id: UUID
    from_account_id: UUID
    to_account_id: UUID
    amount: Decimal
    status: str
    requested_at: datetime
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ── ReconciliationRecord ──────────────────────────────────────────────────────

class ReconciliationCreate(BaseModel):
    account_id: UUID
    notes: Optional[str] = None


class ReconciliationResponse(BaseModel):
    reconciliation_id: UUID
    company_id: UUID
    account_id: UUID
    status: str
    opened_at: datetime
    closed_at: Optional[datetime] = None
    opened_by: UUID
    closed_by: Optional[UUID] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


# ── MovementReconciliation ────────────────────────────────────────────────────

class MarkMovementReconciledBody(BaseModel):
    reconciliation_id: UUID


class MovementReconciliationResponse(BaseModel):
    id: UUID
    company_id: UUID
    movement_id: UUID
    reconciliation_id: UUID
    reconciled_at: datetime
    reconciled_by: UUID

    model_config = {"from_attributes": True}


# ── CashCount ─────────────────────────────────────────────────────────────────

class CashCountCreate(BaseModel):
    account_id: UUID
    counted_amount: Decimal = Field(..., ge=0)
    resolution: str = Field(..., pattern="^(ADJUSTED|NO_ADJUSTMENT)$")
    notes: Optional[str] = None


class CashCountResponse(BaseModel):
    cash_count_id: UUID
    company_id: UUID
    account_id: UUID
    expected_amount: Decimal
    counted_amount: Decimal
    discrepancy: Decimal
    resolution: str
    notes: Optional[str] = None
    entry_id: Optional[UUID] = None
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
