from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PayableInstallmentPlanItem(BaseModel):
    amount: Decimal = Field(..., gt=0)
    due_date: Optional[date] = None


class PayableCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    total_amount: Decimal = Field(..., gt=0)
    supplier_id: Optional[UUID] = None
    due_date: Optional[date] = None
    closing_method: str = "CASH_AT_CREATION"  # CASH_AT_CREATION | INSTALLMENTS
    installments: Optional[List[PayableInstallmentPlanItem]] = None


class PayablePayRequest(BaseModel):
    payment_id: Optional[UUID] = None
    account_id: Optional[UUID] = None


class PayableCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class PayableInstallmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payable_id: UUID
    amount: Decimal
    due_date: Optional[date] = None
    paid_at: Optional[datetime] = None
    payment_id: Optional[UUID] = None
    installment_number: int
    status: str


class PayableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    supplier_id: Optional[UUID] = None
    description: str
    total_amount: Decimal
    paid_amount: Decimal
    status: str
    due_date: Optional[date] = None
    closing_method: str
    source_type: str
    source_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
