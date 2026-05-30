from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role, get_current_company_id
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.user import User
from app.modules.categories import schemas, service

router = APIRouter(prefix="/categories", tags=["categories"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")


@router.get("/", response_model=List[schemas.CategoryResponse])
def list_categories(
    entity_type: Optional[str] = Query(None, description="Filtrar por SERVICE | PRODUCT | EXPENSE"),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.list_categories(db, company_id, entity_type)


@router.post("/", response_model=schemas.CategoryResponse, status_code=201)
def create_category(
    body: schemas.CategoryCreate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.create_category(db, company_id, body)


@router.patch("/{category_id}", response_model=schemas.CategoryResponse)
def patch_category(
    category_id: UUID,
    body: schemas.CategoryPatch,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.patch_category(db, company_id, category_id, body)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    service.delete_category(db, company_id, category_id)
