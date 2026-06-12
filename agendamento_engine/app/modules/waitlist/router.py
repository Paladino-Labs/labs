from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import WaitlistEntry
from app.modules.waitlist import service as waitlist_service
from app.modules.waitlist.schemas import (
    WaitlistConfigResponse,
    WaitlistConfigUpdate,
    WaitlistEntryCreate,
    WaitlistEntryResponse,
)

router = APIRouter(prefix="/waitlist", tags=["waitlist"])


@router.get("/config", response_model=WaitlistConfigResponse)
def get_config(
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return waitlist_service.get_or_create_config(db, current_user.company_id)


@router.put("/config", response_model=WaitlistConfigResponse)
def update_config(
    body: WaitlistConfigUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    config = waitlist_service.get_or_create_config(db, current_user.company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config


@router.get("/entries", response_model=List[WaitlistEntryResponse])
def list_entries(
    status: Optional[str] = Query(None),
    scope_type: Optional[str] = Query(None),
    customer_id: Optional[UUID] = Query(None),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    query = db.query(WaitlistEntry).filter(
        WaitlistEntry.company_id == current_user.company_id
    )
    if status:
        query = query.filter(WaitlistEntry.status == status)
    if scope_type:
        query = query.filter(WaitlistEntry.scope_type == scope_type)
    if customer_id:
        query = query.filter(WaitlistEntry.customer_id == customer_id)
    return query.order_by(
        WaitlistEntry.priority.desc(), WaitlistEntry.created_at.asc(),
    ).limit(200).all()


@router.post("/entries", response_model=WaitlistEntryResponse, status_code=201)
def join(
    body: WaitlistEntryCreate,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return waitlist_service.join_waitlist(
        db,
        company_id=current_user.company_id,
        customer_id=body.customer_id,
        scope_type=body.scope_type,
        service_id=body.service_id,
        professional_id=body.professional_id,
        product_id=body.product_id,
        source_channel="PAINEL",
    )


@router.delete("/entries/{entry_id}", response_model=WaitlistEntryResponse)
def cancel(
    entry_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return waitlist_service.cancel_entry(db, current_user.company_id, entry_id)
