from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.payables import service as payables_service
from app.modules.payables.schemas import (
    PayableCancelRequest,
    PayableCreate,
    PayableInstallmentResponse,
    PayablePayRequest,
    PayableResponse,
)

router = APIRouter(prefix="/payables", tags=["payables"])


@router.get("/", response_model=List[PayableResponse])
def list_payables(
    status: Optional[str] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    due_date_from: Optional[date] = Query(None),
    due_date_to: Optional[date] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return payables_service.list_payables(
        company_id=current_user.company_id,
        db=db,
        status=status,
        supplier_id=supplier_id,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
    )


@router.post("/", response_model=PayableResponse, status_code=201)
def create_payable(
    body: PayableCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Criação manual de conta a pagar (source_type=MANUAL)."""
    return payables_service.create_payable(
        company_id=current_user.company_id,
        description=body.description,
        total_amount=body.total_amount,
        source_type="MANUAL",
        created_by=current_user.id,
        db=db,
        supplier_id=body.supplier_id,
        closing_method=body.closing_method,
        installments=(
            [i.model_dump() for i in body.installments] if body.installments else None
        ),
        due_date=body.due_date,
    )


@router.get("/{payable_id}/installments", response_model=List[PayableInstallmentResponse])
def list_installments(
    payable_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    payables_service.get_payable(payable_id, current_user.company_id, db)
    return payables_service.list_installments(payable_id, current_user.company_id, db)


@router.patch(
    "/{payable_id}/installments/{installment_id}/pay",
    response_model=PayableResponse,
)
def pay_installment(
    payable_id: UUID,
    installment_id: UUID,
    body: PayablePayRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return payables_service.pay_installment(
        payable_id=payable_id,
        installment_id=installment_id,
        company_id=current_user.company_id,
        db=db,
        payment_id=body.payment_id,
        account_id=body.account_id,
    )


@router.patch("/{payable_id}/cancel", response_model=PayableResponse)
def cancel_payable(
    payable_id: UUID,
    body: PayableCancelRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return payables_service.cancel_payable(
        payable_id=payable_id,
        company_id=current_user.company_id,
        reason=body.reason,
        db=db,
        actor_id=current_user.id,
        actor_role=current_user.role,
    )
