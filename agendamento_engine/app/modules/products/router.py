from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id
from app.modules.products import schemas, service

router = APIRouter(prefix="/products", tags=["products"])


@router.get("/", response_model=List[schemas.ProductResponse])
def list_products(
    active_only: bool = True,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.list_products(db, company_id, active_only=active_only)


@router.post("/", response_model=schemas.ProductResponse, status_code=201)
def create_product(
    body: schemas.ProductCreate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.create_product(db, company_id, body)


@router.get("/{product_id}", response_model=schemas.ProductResponse)
def get_product(
    product_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.get_product_or_404(db, company_id, product_id)


@router.patch("/{product_id}", response_model=schemas.ProductResponse)
def update_product(
    product_id: UUID,
    body: schemas.ProductUpdate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.update_product(db, company_id, product_id, body)
