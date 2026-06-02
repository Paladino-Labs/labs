from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.modules.payments.service import RefundReason


# ── PaymentSource ─────────────────────────────────────────────────────────────

class PaymentSourceCreate(BaseModel):
    customer_id: UUID
    type: str               # CARD_CREDIT | CARD_DEBIT
    provider: str
    external_token: str
    last4: Optional[str] = None
    brand: Optional[str] = None


class PaymentSourceResponse(BaseModel):
    source_id: UUID
    company_id: UUID
    customer_id: UUID
    type: str
    provider: str
    last4: Optional[str] = None
    brand: Optional[str] = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Payment ───────────────────────────────────────────────────────────────────

class PaymentCreate(BaseModel):
    customer_id: Optional[UUID] = None
    appointment_id: Optional[UUID] = None
    gross_amount: Decimal
    payment_method: str        # CASH | PIX | BOLETO | CARD_CREDIT | CARD_DEBIT | MAQUININHA
    provider: str
    target_account_id: UUID
    payment_source_id: Optional[UUID] = None
    # Campos usados para registro no Asaas (obrigatórios para PIX/BOLETO)
    customer_cpf_cnpj: Optional[str] = None   # apenas dígitos, e.g. "12345678901"
    due_date: Optional[date] = None            # padrão: hoje


class PaymentResponse(BaseModel):
    payment_id: UUID
    company_id: UUID
    customer_id: Optional[UUID] = None
    appointment_id: Optional[UUID] = None
    currency: str
    gross_catalog_amount: Decimal
    discount_amount: Decimal
    net_charged_amount: Decimal
    provider_fee: Decimal
    payment_method: str
    payment_source_id: Optional[UUID] = None
    provider: str
    target_account_id: UUID
    external_charge_id: Optional[str] = None
    status: str
    manual_override_count: int
    created_at: datetime
    paid_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class RefundRequest(BaseModel):
    reason: RefundReason


# ── DepositPolicy ─────────────────────────────────────────────────────────────

class DepositPolicyCreate(BaseModel):
    service_id: Optional[UUID] = None
    deposit_type: str          # FIXED_AMOUNT | PERCENTAGE
    deposit_value: Decimal
    refundable_until_hours_before: int = 24
    refund_on_tenant_fault: bool = True
    retain_on_no_show: bool = True
    commission_on_retained_deposit: bool = False


class DepositPolicyUpdate(BaseModel):
    deposit_type: Optional[str] = None
    deposit_value: Optional[Decimal] = None
    refundable_until_hours_before: Optional[int] = None
    refund_on_tenant_fault: Optional[bool] = None
    retain_on_no_show: Optional[bool] = None
    commission_on_retained_deposit: Optional[bool] = None


class DepositPolicyResponse(BaseModel):
    policy_id: UUID
    company_id: UUID
    service_id: Optional[UUID] = None
    deposit_type: str
    deposit_value: Decimal
    refundable_until_hours_before: int
    refund_on_tenant_fault: bool
    retain_on_no_show: bool
    commission_on_retained_deposit: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Asaas / Financial Settings ────────────────────────────────────────────────

class AsaasAccountStatusWebhook(BaseModel):
    event: str
    account: Optional[dict] = None
    accountStatus: Optional[str] = None


class FinancialSettingsResponse(BaseModel):
    payment_provider: Optional[str] = None
    external_account_id: Optional[str] = None
    external_account_status: Optional[str] = None
    external_account_created_at: Optional[datetime] = None
    accounts_count: int = 0
