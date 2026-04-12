from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.schemas.client_schema import ClientCreate, ClientOut, ClientUpdate
from app.core.deps import get_current_user
from app.db.session import get_db
from app.modules.customers.service import (
    create_customer,
    get_customer_or_404,
    list_customers,
    update_customer,
)

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("/", response_model=ClientOut, status_code=201)
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return create_customer(db, current_user.company_id, data)


@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return list_customers(db, current_user.company_id)


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return get_customer_or_404(db, current_user.company_id, client_id)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(
    client_id: UUID,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    customer = get_customer_or_404(db, current_user.company_id, client_id)
    return update_customer(db, customer, data)
