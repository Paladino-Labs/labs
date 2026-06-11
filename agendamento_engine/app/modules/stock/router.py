from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.stock import service as stock_service
from app.modules.stock.schemas import (
    ReceiveOrderRequest,
    ReceiveOrderResponse,
    RecordMovementRequest,
    StockMovementResponse,
    StockProductResponse,
    SupplierOrderResponse,
)

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/", response_model=List[StockProductResponse])
def list_stock(
    active_only: bool = Query(True),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Produtos com stock atual + avg_cost."""
    return stock_service.list_stock(
        company_id=current_user.company_id, db=db, active_only=active_only
    )


@router.post("/orders/", response_model=ReceiveOrderResponse, status_code=201)
def receive_order(
    body: ReceiveOrderRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    order, payable = stock_service.receive_order(
        company_id=current_user.company_id,
        supplier_id=body.supplier_id,
        items=[item.model_dump() for item in body.items],
        created_by=current_user.id,
        db=db,
        closing_method=body.closing_method,
        installments=(
            [i.model_dump() for i in body.installments] if body.installments else None
        ),
        due_date=body.due_date,
        notes=body.notes,
    )
    return ReceiveOrderResponse(
        order=SupplierOrderResponse.model_validate(order),
        payable_id=payable.id,
        total_amount=payable.total_amount,
    )


@router.post("/movements/", response_model=StockMovementResponse, status_code=201)
def record_movement(
    body: RecordMovementRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return stock_service.record_movement(
        company_id=current_user.company_id,
        product_id=body.product_id,
        movement_type=body.movement_type,
        quantity=body.quantity,
        created_by=current_user.id,
        db=db,
        source_type=body.source_type,
        source_id=body.source_id,
        notes=body.notes,
        actor_role=current_user.role,
    )


@router.get("/movements/", response_model=List[StockMovementResponse])
def list_movements(
    product_id: Optional[UUID] = Query(None),
    movement_type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return stock_service.list_movements(
        company_id=current_user.company_id,
        db=db,
        product_id=product_id,
        movement_type=movement_type,
        date_from=date_from,
        date_to=date_to,
    )
