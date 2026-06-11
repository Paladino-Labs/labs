from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReceiveOrderItem(BaseModel):
    product_id: UUID
    quantity: Decimal = Field(..., gt=0)
    unit_cost: Decimal = Field(..., ge=0)


class InstallmentPlanItem(BaseModel):
    amount: Decimal = Field(..., gt=0)
    due_date: Optional[date] = None


class ReceiveOrderRequest(BaseModel):
    supplier_id: Optional[UUID] = None
    items: List[ReceiveOrderItem] = Field(..., min_length=1)
    closing_method: str = "CASH_AT_CREATION"  # CASH_AT_CREATION | INSTALLMENTS
    installments: Optional[List[InstallmentPlanItem]] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class RecordMovementRequest(BaseModel):
    product_id: UUID
    movement_type: str  # VENDA | USO_INTERNO | PERDA | AJUSTE
    quantity: Decimal
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    notes: Optional[str] = None


class StockMovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    product_id: UUID
    movement_type: str
    quantity: Decimal
    unit_cost: Optional[Decimal] = None
    source_type: Optional[str] = None
    source_id: Optional[UUID] = None
    notes: Optional[str] = None
    occurred_at: datetime
    created_by: UUID


class SupplierOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    supplier_id: Optional[UUID] = None
    status: str
    ordered_at: datetime
    received_at: Optional[datetime] = None
    notes: Optional[str] = None


class StockProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    active: bool
    stock: Optional[int] = None
    stock_min_alert: Optional[Decimal] = None
    unit: Optional[str] = None
    avg_cost: Optional[Decimal] = None


class ReceiveOrderResponse(BaseModel):
    order: SupplierOrderResponse
    payable_id: UUID
    total_amount: Decimal
