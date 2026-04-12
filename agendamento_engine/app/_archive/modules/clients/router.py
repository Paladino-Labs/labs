from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.schemas.client_schema import ClientCreate, ClientOut
from app.db.session import get_db
from app.db.models import Client
from app.core.deps import get_current_user

router = APIRouter(prefix="/clients", tags=["Clients"])


@router.post("/", response_model=list[ClientOut])
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    client = Client(
        company_id=current_user.company_id,
        name=data.name,
        phone=data.phone
    )

    db.add(client)
    db.commit()
    db.refresh(client)

    return client

@router.get("/", response_model=list[ClientOut])
def list_clients(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    return db.query(Client).filter(
        Client.company_id == current_user.company_id
    ).all()