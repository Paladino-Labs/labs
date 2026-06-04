"""Routers do Financial Core.

Endpoints Sprint 6:
    GET    /financial/accounts
    POST   /financial/accounts
    GET    /financial/accounts/{id}/balance
    GET    /financial/movements
    GET    /financial/entries
    GET    /financial/dre
    POST   /financial/manual-adjustment

Endpoints Sprint 7:
    POST   /financial/transfers
    GET    /financial/transfers
    POST   /financial/reconciliation
    PUT    /financial/reconciliation/{id}/close
    GET    /financial/movements/unreconciled
    POST   /financial/movements/{id}/reconcile
    GET    /financial/cash-counts
    POST   /financial/cash-counts
"""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_current_company_id, require_role
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.user import User
from app.modules.financial_core import service
from app.modules.financial_core import transfer_service, reconciliation_service, cash_count_service
from app.modules.financial_core.schemas import (
    AccountCreate,
    AccountResponse,
    BalanceResponse,
    MovementFilters,
    MovementResponse,
    EntryFilters,
    EntryResponse,
    DreResponse,
    FeePolicyResponse,
    FeePolicyUpdate,
    ManualAdjustmentCreate,
    TransferCreate,
    TransferResponse,
    ReconciliationCreate,
    ReconciliationResponse,
    MarkMovementReconciledBody,
    MovementReconciliationResponse,
    CashCountCreate,
    CashCountResponse,
)

router = APIRouter(prefix="/financial", tags=["financial"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")
_owner_admin_operator = require_role("OWNER", "ADMIN", "OPERATOR", "PLATFORM_OWNER")


# ── Accounts ──────────────────────────────────────────────────────────────────

@router.get("/accounts", response_model=List[AccountResponse])
def list_accounts(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.list_accounts(company_id, db)


@router.post("/accounts", response_model=AccountResponse, status_code=201)
def create_account(
    body: AccountCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.create_account(
        company_id=company_id,
        name=body.name,
        type=body.type,
        provider=body.provider,
        external_ref=body.external_ref,
        currency=body.currency,
        is_default_inflow=body.is_default_inflow,
        db=db,
    )


@router.get("/accounts/{account_id}/balance", response_model=BalanceResponse)
def get_account_balance(
    account_id: UUID,
    as_of: Optional[datetime] = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    # Valida que conta pertence ao tenant
    service.get_account(account_id, company_id, db)
    balance = service.compute_balance(
        account_id=account_id,
        as_of=as_of,
        company_id=company_id,
        db=db,
    )
    return BalanceResponse(account_id=account_id, balance=balance, as_of=as_of)


# ── Movements ─────────────────────────────────────────────────────────────────

@router.get("/movements", response_model=List[MovementResponse])
def list_movements(
    account_id: Optional[UUID] = Query(None),
    type: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    filters = MovementFilters(
        account_id=account_id,
        type=type,
        date_from=date_from,
        date_to=date_to,
    )
    return service.list_movements(company_id, filters, db)


# ── Entries ───────────────────────────────────────────────────────────────────

@router.get("/entries", response_model=List[EntryResponse])
def list_entries(
    type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    date_from: Optional[datetime] = Query(None),
    date_to: Optional[datetime] = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    filters = EntryFilters(
        type=type,
        category=category,
        date_from=date_from,
        date_to=date_to,
    )
    return service.list_entries(company_id, filters, db)


# ── DRE ───────────────────────────────────────────────────────────────────────

@router.get("/dre", response_model=DreResponse)
def get_dre(
    date_from: datetime = Query(...),
    date_to: datetime = Query(...),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    result = service.aggregate_dre(
        company_id=company_id,
        date_from=date_from,
        date_to=date_to,
        db=db,
    )
    return DreResponse(**result)


# ── Manual Adjustment ─────────────────────────────────────────────────────────

@router.post("/manual-adjustment", status_code=201)
def create_manual_adjustment(
    body: ManualAdjustmentCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    movement, entry = service.create_manual_adjustment(
        amount=body.amount,
        direction=body.direction,
        category=body.category,
        account_id=body.account_id,
        reason=body.reason,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )
    return {
        "movement_id": movement.movement_id,
        "entry_id": entry.entry_id,
        "amount": movement.amount,
        "direction": body.direction,
        "category": body.category,
    }


# ── Transfers (Sprint 7) ──────────────────────────────────────────────────────

@router.post("/transfers", response_model=TransferResponse, status_code=201)
def create_transfer(
    body: TransferCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return transfer_service.create_transfer(
        from_account_id=body.from_account_id,
        to_account_id=body.to_account_id,
        amount=body.amount,
        notes=body.notes,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )


@router.get("/transfers", response_model=List[TransferResponse])
def list_transfers(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return transfer_service.list_transfers(company_id, db)


# ── Reconciliation (Sprint 7) ─────────────────────────────────────────────────

@router.post("/reconciliation", response_model=ReconciliationResponse, status_code=201)
def open_reconciliation(
    body: ReconciliationCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return reconciliation_service.open_reconciliation(
        account_id=body.account_id,
        notes=body.notes,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )


@router.put("/reconciliation/{reconciliation_id}/close", response_model=ReconciliationResponse)
def close_reconciliation(
    reconciliation_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return reconciliation_service.close_reconciliation(
        reconciliation_id=reconciliation_id,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )


@router.get("/movements/unreconciled", response_model=List[MovementResponse])
def list_unreconciled_movements(
    account_id: UUID = Query(...),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return reconciliation_service.list_unreconciled_movements(
        account_id=account_id,
        company_id=company_id,
        db=db,
    )


@router.post("/movements/{movement_id}/reconcile", response_model=MovementReconciliationResponse, status_code=201)
def mark_movement_reconciled(
    movement_id: UUID,
    body: MarkMovementReconciledBody,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return reconciliation_service.mark_movement_reconciled(
        movement_id=movement_id,
        reconciliation_id=body.reconciliation_id,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )


# ── Cash Counts (Sprint 7) ────────────────────────────────────────────────────

@router.get("/cash-counts", response_model=List[CashCountResponse])
def list_cash_counts(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    return cash_count_service.list_cash_counts(company_id, db)


@router.post("/cash-counts", response_model=CashCountResponse, status_code=201)
def record_cash_count(
    body: CashCountCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    return cash_count_service.record_count(
        account_id=body.account_id,
        counted_amount=body.counted_amount,
        resolution=body.resolution,
        notes=body.notes,
        actor_id=actor.id,
        company_id=company_id,
        db=db,
    )


# ── Fee Policies (Sprint 11) ──────────────────────────────────────────────────

@router.get("/fee-policies", response_model=List[FeePolicyResponse])
def list_fee_policies(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    """Lista todas as políticas de taxa MDR do tenant (7 registros por tenant)."""
    return service.list_fee_routing_policies(company_id, db)


@router.patch("/fee-policies/{fee_source}", response_model=FeePolicyResponse)
def update_fee_policy(
    fee_source: str,
    body: FeePolicyUpdate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    """Atualiza taxa MDR de um fee_source do tenant.

    fee_source deve existir nas políticas do tenant (criadas em create_company).
    Retorna HTTP 404 se não encontrado.
    """
    return service.update_fee_policy_calculation(
        fee_source=fee_source,
        company_id=company_id,
        db=db,
        fee_percentage=body.fee_percentage,
        fee_flat=body.fee_flat,
        is_active=body.is_active,
    )
