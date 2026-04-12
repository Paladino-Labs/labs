from uuid import UUID
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, require_admin
from app.modules.customers import schemas, service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=List[schemas.CustomerResponse])
def list_customers(
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.list_customers(db, company_id)


@router.post("/", response_model=schemas.CustomerResponse, status_code=201)
def create_customer(
    body: schemas.CustomerCreate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.create_customer(db, company_id, body)


@router.get("/{customer_id}", response_model=schemas.CustomerResponse)
def get_customer(
    customer_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.get_customer_or_404(db, company_id, customer_id)


@router.patch("/{customer_id}", response_model=schemas.CustomerResponse)
def update_customer(
    customer_id: UUID,
    body: schemas.CustomerUpdate,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return service.update_customer(db, company_id, customer_id, body)
