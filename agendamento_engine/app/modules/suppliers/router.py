from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role
from app.infrastructure.db.session import get_db
from app.modules.suppliers import service as supplier_service
from app.modules.suppliers.schemas import (
    SupplierCreate,
    SupplierResponse,
    SupplierUpdate,
)

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


@router.get("/", response_model=List[SupplierResponse])
def list_suppliers(
    active: Optional[bool] = Query(True),
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    return supplier_service.list_suppliers(
        company_id=current_user.company_id, db=db, active=active
    )


@router.post("/", response_model=SupplierResponse, status_code=201)
def create_supplier(
    body: SupplierCreate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return supplier_service.create_supplier(
        company_id=current_user.company_id, data=body.model_dump(), db=db
    )


@router.patch("/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: UUID,
    body: SupplierUpdate,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    return supplier_service.update_supplier(
        supplier_id=supplier_id,
        company_id=current_user.company_id,
        data=body.model_dump(exclude_unset=True),
        db=db,
    )


@router.delete("/{supplier_id}", response_model=SupplierResponse)
def deactivate_supplier(
    supplier_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN")),
    db: Session = Depends(get_db),
):
    """Soft delete — fornecedor nunca é apagado (Princípio 10)."""
    return supplier_service.deactivate_supplier(
        supplier_id=supplier_id, company_id=current_user.company_id, db=db
    )
