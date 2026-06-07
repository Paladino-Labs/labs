from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.customer_credit import service as credit_service
from app.modules.customer_credit.schemas import (
    BalanceItem,
    CustomerCreditResponse,
    GrantCotaRequest,
    RevokeRequest,
)

router = APIRouter(tags=["customer-credits"])


@router.get("/customer-credits", response_model=List[CustomerCreditResponse])
def list_credits(
    customer_id: UUID = Query(...),
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return credit_service.list_credits(customer_id, current_user.company_id, db)


@router.get("/customer-credits/balance", response_model=List[BalanceItem])
def get_balance(
    customer_id: UUID = Query(...),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return credit_service.get_balance(customer_id, current_user.company_id, db)


@router.post("/customer-credits/grant-cota", response_model=CustomerCreditResponse, status_code=201)
def grant_cota(
    body: GrantCotaRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    credit = credit_service.grant_cota(
        customer_id=body.customer_id,
        total_cotas=body.total_cotas,
        expires_at=body.expires_at,
        reason=body.reason,
        actor_id=current_user.id,
        actor_role=current_user.role,
        company_id=current_user.company_id,
        db=db,
    )
    db.commit()
    db.refresh(credit)
    return credit


@router.post("/customer-credits/{credit_id}/revoke", response_model=CustomerCreditResponse)
def revoke_credit(
    credit_id: UUID,
    body: RevokeRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    credit = credit_service.revoke(
        credit_id=credit_id,
        reason=body.reason,
        actor_id=current_user.id,
        actor_role=current_user.role,
        company_id=current_user.company_id,
        db=db,
    )
    db.commit()
    db.refresh(credit)
    return credit
