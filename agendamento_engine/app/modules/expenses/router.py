from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.expenses import service as expense_service
from app.modules.expenses.schemas import (
    ExpenseCancelRequest,
    ExpenseCreate,
    ExpensePayRequest,
    ExpenseResponse,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.post("/", response_model=ExpenseResponse, status_code=201)
def create_expense(
    body: ExpenseCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    data = body.model_dump()
    if data.get("recurrence_rule"):
        rule = data["recurrence_rule"]
        if rule.get("end_date"):
            rule["end_date"] = rule["end_date"].isoformat()
    return expense_service.create_expense(
        company_id=current_user.company_id,
        data=data,
        created_by=current_user.id,
        db=db,
    )


@router.get("/", response_model=List[ExpenseResponse])
def list_expenses(
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    due_date_from: Optional[date] = Query(None),
    due_date_to: Optional[date] = Query(None),
    supplier_id: Optional[UUID] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return expense_service.get_expenses(
        company_id=current_user.company_id,
        db=db,
        status=status,
        category=category,
        due_date_from=due_date_from,
        due_date_to=due_date_to,
        supplier_id=supplier_id,
    )


@router.get("/{expense_id}", response_model=ExpenseResponse)
def get_expense(
    expense_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return expense_service.get_expense(expense_id, current_user.company_id, db)


@router.patch("/{expense_id}/pay", response_model=ExpenseResponse)
def pay_expense(
    expense_id: UUID,
    body: ExpensePayRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return expense_service.pay_expense(
        expense_id=expense_id,
        company_id=current_user.company_id,
        db=db,
        paid_amount=body.paid_amount,
    )


@router.patch("/{expense_id}/cancel", response_model=ExpenseResponse)
def cancel_expense(
    expense_id: UUID,
    body: ExpenseCancelRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return expense_service.cancel_expense(
        expense_id=expense_id,
        company_id=current_user.company_id,
        reason=body.reason,
        db=db,
        actor_id=current_user.id,
    )
