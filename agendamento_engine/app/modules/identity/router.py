"""
Rotas de consentimento (tenant) + stub do Portal — Sprint A.

Tenants gerenciam consents dos PRÓPRIOS clientes: o acesso parte sempre
do Customer tenant-scoped (get_customer_or_404 garante o isolamento);
a identity global nunca é consultada diretamente por query do tenant.
"""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_current_company_id, require_role
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import Customer, User
from app.modules.customers.service import get_customer_or_404
from app.modules.identity import consent_service
from app.modules.identity.consent_service import SourceChannel
from app.modules.identity.resolver import resolver
from app.modules.identity.schemas import (
    ConsentChangeRequest,
    ConsentRecordResponse,
    IdentityResponse,
)

router = APIRouter(tags=["identity"])


def _identity_id_for(db: Session, customer: Customer) -> UUID:
    """
    identity_id do customer; se NULL (cliente pré-backfill), resolve pelo
    telefone e vincula on-the-fly.
    """
    if customer.identity_id is not None:
        return customer.identity_id
    result = resolver.resolve(db, customer.phone, name=customer.name)
    customer.identity_id = result.identity_id
    db.commit()
    return result.identity_id


@router.get(
    "/customers/{customer_id}/consents",
    response_model=List[ConsentRecordResponse],
)
def list_customer_consents(
    customer_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    """Consents vigentes do cliente (último status por tipo+canal)."""
    customer = get_customer_or_404(db, company_id, customer_id)
    if customer.identity_id is None:
        return []
    return consent_service.get_consents_for_identity(
        db, customer.identity_id, company_id
    )


@router.post(
    "/customers/{customer_id}/consents/grant",
    response_model=ConsentRecordResponse,
    status_code=201,
)
def grant_customer_consent(
    customer_id: UUID,
    body: ConsentChangeRequest,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    customer = get_customer_or_404(db, company_id, customer_id)
    identity_id = _identity_id_for(db, customer)
    return consent_service.grant_consent(
        db, identity_id, company_id, body.consent_type, body.channel,
        SourceChannel.PAINEL, notes=body.notes,
    )


@router.post(
    "/customers/{customer_id}/consents/revoke",
    response_model=ConsentRecordResponse,
    status_code=201,
)
def revoke_customer_consent(
    customer_id: UUID,
    body: ConsentChangeRequest,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    customer = get_customer_or_404(db, company_id, customer_id)
    identity_id = _identity_id_for(db, customer)
    return consent_service.revoke_consent(
        db, identity_id, company_id, body.consent_type, body.channel,
        SourceChannel.PAINEL, notes=body.notes,
    )


@router.get("/identity/me", response_model=IdentityResponse)
def get_my_identity():
    """
    Dados da própria identity (cliente final). Requer identity_id no JWT —
    o JWT de cliente (claims separados, sem company_id) é entregue pelo
    Sprint D (Portal). Até lá: 501.
    """
    raise HTTPException(
        status_code=501,
        detail="Disponível no Sprint D (Portal do Cliente) — requer JWT de cliente",
    )
