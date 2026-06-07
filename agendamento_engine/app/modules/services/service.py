from decimal import Decimal
from uuid import UUID
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Service
from app.infrastructure.db.models.service import ServicePricingOverride, ServiceVariant
from app.modules.services.schemas import (
    ServiceCreate,
    ServiceUpdate,
    ServiceVariantCreate,
    ServiceVariantUpdate,
    PricingOverrideCreate,
    PricingOverrideUpdate,
)


# ─── Service CRUD ─────────────────────────────────────────────────────────────

def list_services(db: Session, company_id: UUID, active_only: bool = True):
    q = db.query(Service).filter(Service.company_id == company_id)
    if active_only:
        q = q.filter(Service.active == True)
    return q.order_by(Service.name).all()


def get_service_or_404(db: Session, company_id: UUID, service_id: UUID) -> Service:
    s = db.query(Service).filter(
        Service.id == service_id,
        Service.company_id == company_id,
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")
    return s


def create_service(db: Session, company_id: UUID, data: ServiceCreate) -> Service:
    s = Service(company_id=company_id, **data.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def update_service(db: Session, company_id: UUID, service_id: UUID, data: ServiceUpdate) -> Service:
    s = get_service_or_404(db, company_id, service_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    return s


# ─── Preço efetivo ────────────────────────────────────────────────────────────

def get_effective_price(
    db: Session,
    company_id: UUID,
    service_id: UUID,
    professional_id: Optional[UUID] = None,
    variant_id: Optional[UUID] = None,
) -> tuple[Decimal, int]:
    """
    Retorna (price, duration_minutes) com prioridade:
    1. ServiceVariant (se variant_id fornecido e ativa)
    2. ServicePricingOverride (se existe para professional_id + is_active)
    3. Service.price / Service.duration (fallback)
    """
    service = db.query(Service).filter(
        Service.id == service_id,
        Service.company_id == company_id,
    ).first()
    if not service:
        raise HTTPException(status_code=404, detail="Serviço não encontrado")

    # 1. Variante
    if variant_id:
        variant = db.query(ServiceVariant).filter(
            ServiceVariant.variant_id == variant_id,
            ServiceVariant.service_id == service_id,
            ServiceVariant.company_id == company_id,
            ServiceVariant.is_active == True,
        ).first()
        if variant:
            return (variant.price, variant.duration_min)

    # 2. Override por profissional
    if professional_id:
        override = db.query(ServicePricingOverride).filter(
            ServicePricingOverride.professional_id == professional_id,
            ServicePricingOverride.service_id == service_id,
            ServicePricingOverride.company_id == company_id,
            ServicePricingOverride.is_active == True,
        ).first()
        if override:
            duration = override.duration_min if override.duration_min is not None else service.duration
            return (override.price, duration)

    # 3. Fallback: serviço base
    return (service.price, service.duration)


# ─── ServiceVariant CRUD ──────────────────────────────────────────────────────

def list_variants(db: Session, company_id: UUID, service_id: UUID) -> list:
    get_service_or_404(db, company_id, service_id)
    return (
        db.query(ServiceVariant)
        .filter(
            ServiceVariant.service_id == service_id,
            ServiceVariant.company_id == company_id,
        )
        .order_by(ServiceVariant.sort_order, ServiceVariant.name)
        .all()
    )


def create_variant(
    db: Session, company_id: UUID, service_id: UUID, data: ServiceVariantCreate
) -> ServiceVariant:
    get_service_or_404(db, company_id, service_id)
    v = ServiceVariant(
        company_id=company_id,
        service_id=service_id,
        **data.model_dump(),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def update_variant(
    db: Session, company_id: UUID, service_id: UUID, variant_id: UUID, data: ServiceVariantUpdate
) -> ServiceVariant:
    v = db.query(ServiceVariant).filter(
        ServiceVariant.variant_id == variant_id,
        ServiceVariant.service_id == service_id,
        ServiceVariant.company_id == company_id,
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="Variante não encontrada")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(v, field, value)
    db.commit()
    db.refresh(v)
    return v


def delete_variant(
    db: Session, company_id: UUID, service_id: UUID, variant_id: UUID
) -> None:
    v = db.query(ServiceVariant).filter(
        ServiceVariant.variant_id == variant_id,
        ServiceVariant.service_id == service_id,
        ServiceVariant.company_id == company_id,
    ).first()
    if not v:
        raise HTTPException(status_code=404, detail="Variante não encontrada")
    db.delete(v)
    db.commit()


# ─── ServicePricingOverride CRUD ──────────────────────────────────────────────

def _get_professional_or_404(db: Session, company_id: UUID, professional_id: UUID):
    from app.infrastructure.db.models.professional import Professional
    p = db.query(Professional).filter(
        Professional.id == professional_id,
        Professional.company_id == company_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")
    return p


def list_overrides(db: Session, company_id: UUID, professional_id: UUID) -> list:
    _get_professional_or_404(db, company_id, professional_id)
    return (
        db.query(ServicePricingOverride)
        .filter(
            ServicePricingOverride.professional_id == professional_id,
            ServicePricingOverride.company_id == company_id,
        )
        .all()
    )


def create_override(
    db: Session, company_id: UUID, professional_id: UUID, data: PricingOverrideCreate
) -> ServicePricingOverride:
    _get_professional_or_404(db, company_id, professional_id)
    get_service_or_404(db, company_id, data.service_id)

    o = ServicePricingOverride(
        company_id=company_id,
        professional_id=professional_id,
        service_id=data.service_id,
        price=data.price,
        duration_min=data.duration_min,
    )
    db.add(o)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Override já existe para este profissional e serviço",
        )
    db.refresh(o)
    return o


def update_override(
    db: Session, company_id: UUID, professional_id: UUID, override_id: UUID,
    data: PricingOverrideUpdate,
) -> ServicePricingOverride:
    o = db.query(ServicePricingOverride).filter(
        ServicePricingOverride.override_id == override_id,
        ServicePricingOverride.professional_id == professional_id,
        ServicePricingOverride.company_id == company_id,
    ).first()
    if not o:
        raise HTTPException(status_code=404, detail="Override não encontrado")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(o, field, value)
    db.commit()
    db.refresh(o)
    return o


def delete_override(
    db: Session, company_id: UUID, professional_id: UUID, override_id: UUID
) -> None:
    o = db.query(ServicePricingOverride).filter(
        ServicePricingOverride.override_id == override_id,
        ServicePricingOverride.professional_id == professional_id,
        ServicePricingOverride.company_id == company_id,
    ).first()
    if not o:
        raise HTTPException(status_code=404, detail="Override não encontrado")
    db.delete(o)
    db.commit()
