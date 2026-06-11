from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RecurrenceRule(BaseModel):
    frequency: str = Field(..., description="Apenas MONTHLY no Estágio 0")
    day_of_month: int = Field(..., ge=1, le=31)
    end_date: Optional[date] = None


class ExpenseCreate(BaseModel):
    description: str = Field(..., min_length=1, max_length=255)
    amount: Decimal = Field(..., gt=0)
    category: str = Field(..., max_length=50)
    due_date: date
    supplier_id: Optional[UUID] = None
    recurrence_rule: Optional[RecurrenceRule] = None


class ExpensePayRequest(BaseModel):
    paid_amount: Optional[Decimal] = Field(None, gt=0)


class ExpenseCancelRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class ExpenseResponse(BaseModel):
    id: UUID
    company_id: UUID
    description: str
    amount: Decimal
    category: str
    supplier_id: Optional[UUID] = None
    due_date: date
    status: str
    paid_at: Optional[datetime] = None
    paid_amount: Optional[Decimal] = None
    recurrence_rule: Optional[dict] = None
    parent_expense_id: Optional[UUID] = None
    created_by: UUID
    created_at: datetime

    model_config = {"from_attributes": True}
