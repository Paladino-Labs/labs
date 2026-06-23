from uuid import UUID
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.infrastructure.db.session import get_db
from app.core.deps import get_current_company_id, get_current_user, require_role
from app.infrastructure.db.models.user import User
from app.modules.customers import schemas, service

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=List[schemas.CustomerResponse])
def list_customers(
    company_id: UUID = Depends(get_current_company_id),
    professional_id: Optional[UUID] = Query(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # PROFESSIONAL tem o escopo forçado ao próprio cadastro (mesmo padrão do
    # GET /appointments/ no Sprint 27). Sem vínculo → UUID fictício → lista vazia.
    effective_professional_id = professional_id
    if user.role == "PROFESSIONAL":
        from app.modules.professionals.service import get_linked_professional
        prof = get_linked_professional(db, user.id, company_id)
        effective_professional_id = prof.id if prof else UUID(int=0)
    return service.list_customers(
        db, company_id, professional_id=effective_professional_id
    )


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


@router.get("/{customer_id}/insights")
def get_customer_insights(
    customer_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Insights heurísticos CRM (Sprint H) — exibição interna no painel."""
    from app.modules.crm import service as crm_service
    from app.modules.crm.schemas import InsightsResponse

    service.get_customer_or_404(db, current_user.company_id, customer_id)
    data = crm_service.get_customer_insights(db, customer_id, current_user.company_id)
    return InsightsResponse(**data)


@router.get("/{customer_id}/classification")
def get_customer_classification(
    customer_id: UUID,
    current_user=Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    db: Session = Depends(get_db),
):
    """Última classificação + histórico (últimas 5)."""
    from app.infrastructure.db.models import CustomerClassification
    from app.modules.crm.schemas import ClassificationOut, CustomerClassificationResponse

    service.get_customer_or_404(db, current_user.company_id, customer_id)
    history = (
        db.query(CustomerClassification)
        .filter(
            CustomerClassification.company_id == current_user.company_id,
            CustomerClassification.customer_id == customer_id,
        )
        .order_by(CustomerClassification.computed_at.desc())
        .limit(5)
        .all()
    )
    items = [ClassificationOut.model_validate(h) for h in history]
    return CustomerClassificationResponse(
        current=items[0] if items else None,
        history=items,
    )


@router.get("/{customer_id}/appointments", response_model=List[schemas.CustomerAppointmentItem])
def get_customer_appointments(
    customer_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    """Histórico completo de agendamentos do cliente (ativos + concluídos + cancelados)."""
    return service.list_appointments_for_customer(db, company_id, customer_id)
