from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, model_validator


# ── CommissionPolicy ─────────────────────────────────────────────────────────

class CommissionPolicyCreate(BaseModel):
    professional_id:       Optional[UUID] = None
    service_id:            Optional[UUID] = None
    commission_base:       str   # GROSS_SERVICE | NET_SERVICE | GROSS_OPERATION | CUSTOM_AMOUNT
    commission_fee_policy: str   # BEFORE_FEES | AFTER_FEES
    rate:                  Optional[Decimal] = None
    fixed_amount:          Optional[Decimal] = None

    @model_validator(mode="after")
    def validate_rate_or_fixed(self) -> "CommissionPolicyCreate":
        has_rate  = self.rate is not None
        has_fixed = self.fixed_amount is not None
        if has_rate == has_fixed:
            raise ValueError("Exatamente um de rate ou fixed_amount deve ser fornecido")
        if self.commission_base == "CUSTOM_AMOUNT" and not has_fixed:
            raise ValueError("CUSTOM_AMOUNT requer fixed_amount")
        return self


class CommissionPolicyUpdate(BaseModel):
    commission_base:       Optional[str]     = None
    commission_fee_policy: Optional[str]     = None
    rate:                  Optional[Decimal] = None
    fixed_amount:          Optional[Decimal] = None
    is_active:             Optional[bool]    = None


class CommissionPolicyResponse(BaseModel):
    policy_id:             UUID
    company_id:            UUID
    professional_id:       Optional[UUID]
    service_id:            Optional[UUID]
    commission_base:       str
    commission_fee_policy: str
    rate:                  Optional[Decimal]
    fixed_amount:          Optional[Decimal]
    is_active:             bool
    created_at:            datetime
    updated_at:            Optional[datetime]

    model_config = {"from_attributes": True}


# ── Commission ───────────────────────────────────────────────────────────────

class CommissionResponse(BaseModel):
    commission_id:     UUID
    company_id:        UUID
    professional_id:   UUID
    policy_id:         Optional[UUID]
    appointment_id:    Optional[UUID]
    operation_type:    str
    gross_amount:      Decimal
    commission_amount: Decimal
    status:            str
    due_date:          Optional[date]
    paid_at:           Optional[datetime]
    payout_id:         Optional[UUID]
    created_at:        datetime

    model_config = {"from_attributes": True}


class MarkDueRequest(BaseModel):
    due_date: date


class ReverseRequest(BaseModel):
    reason: str


# ── CommissionPayout ─────────────────────────────────────────────────────────

class CommissionPayoutCreate(BaseModel):
    professional_id: UUID
    commission_ids:  List[UUID]
    account_id:      UUID


class CommissionPayoutResponse(BaseModel):
    payout_id:       UUID
    company_id:      UUID
    professional_id: UUID
    total_amount:    Decimal
    account_id:      UUID
    status:          str
    paid_at:         Optional[datetime]
    created_by:      UUID
    created_at:      datetime

    model_config = {"from_attributes": True}
