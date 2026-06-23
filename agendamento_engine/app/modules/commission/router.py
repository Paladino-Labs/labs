from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_role
from app.infrastructure.db.session import get_db
from app.modules.commission import service as commission_service
from app.modules.commission.schemas import (
    CommissionPayoutCreate,
    CommissionPayoutResponse,
    CommissionPolicyCreate,
    CommissionPolicyResponse,
    CommissionPolicyUpdate,
    CommissionResponse,
    MarkDueRequest,
    ReverseRequest,
)

router = APIRouter(tags=["commissions"])


# ── Políticas ─────────────────────────────────────────────────────────────────

@router.get("/commission-policies", response_model=List[CommissionPolicyResponse])
def list_policies(
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.list_policies(current_user.company_id, db)


@router.post("/commission-policies", response_model=CommissionPolicyResponse, status_code=201)
def create_policy(
    body: CommissionPolicyCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.create_policy(
        company_id=current_user.company_id,
        professional_id=body.professional_id,
        service_id=body.service_id,
        commission_base=body.commission_base,
        commission_fee_policy=body.commission_fee_policy,
        rate=body.rate,
        fixed_amount=body.fixed_amount,
        db=db,
    )


@router.patch("/commission-policies/{policy_id}", response_model=CommissionPolicyResponse)
def update_policy(
    policy_id: UUID,
    body: CommissionPolicyUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.update_policy(
        policy_id=policy_id,
        company_id=current_user.company_id,
        db=db,
        **body.model_dump(exclude_none=True),
    )


@router.delete("/commission-policies/{policy_id}", response_model=CommissionPolicyResponse)
def delete_policy(
    policy_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.delete_policy(policy_id, current_user.company_id, db)


# ── Comissões ─────────────────────────────────────────────────────────────────

@router.get("/commissions/me", response_model=List[CommissionResponse])
def my_commissions(
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Comissões do profissional logado (role=PROFESSIONAL)."""
    if current_user.role != "PROFESSIONAL":
        raise HTTPException(
            status_code=403,
            detail="Apenas profissionais podem acessar este endpoint",
        )
    from app.modules.professionals.service import get_linked_professional

    prof = get_linked_professional(db, current_user.id, current_user.company_id)
    if not prof:
        return []  # sem vínculo = sem comissões (não é erro)
    return commission_service.list_commissions(
        company_id=current_user.company_id,
        db=db,
        professional_id=prof.id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/commissions", response_model=List[CommissionResponse])
def list_commissions(
    professional_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.list_commissions(
        company_id=current_user.company_id,
        db=db,
        professional_id=professional_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.patch("/commissions/{commission_id}/mark-due", response_model=CommissionResponse)
def mark_due(
    commission_id: UUID,
    body: MarkDueRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.mark_due(commission_id, body.due_date, current_user.company_id, db)


@router.patch("/commissions/{commission_id}/reverse", response_model=CommissionResponse)
def reverse_commission(
    commission_id: UUID,
    body: ReverseRequest,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.reverse_commission(
        commission_id=commission_id,
        reason=body.reason,
        actor_id=current_user.id,
        company_id=current_user.company_id,
        db=db,
    )


# ── Payouts ───────────────────────────────────────────────────────────────────

@router.post("/commission-payouts", response_model=CommissionPayoutResponse, status_code=201)
def create_payout(
    body: CommissionPayoutCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.create_payout(
        professional_id=body.professional_id,
        commission_ids=body.commission_ids,
        account_id=body.account_id,
        actor_id=current_user.id,
        company_id=current_user.company_id,
        db=db,
    )


@router.get("/commission-payouts", response_model=List[CommissionPayoutResponse])
def list_payouts(
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.list_payouts(current_user.company_id, db)


@router.get("/commission-payouts/{payout_id}", response_model=CommissionPayoutResponse)
def get_payout(
    payout_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return commission_service.get_payout(payout_id, current_user.company_id, db)
