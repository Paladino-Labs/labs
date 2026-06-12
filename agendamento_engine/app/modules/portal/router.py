"""
Router do Portal do Cliente — Sprint D. Prefixo /portal.

Endpoints de auth são públicos (rate-limited); os demais exigem JWT
portal (type="portal") via get_current_portal_identity — JWT de tenant
é rejeitado com 401.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.core.deps import get_current_portal_identity
from app.core.rate_limit import limiter
from app.infrastructure.db.models import PaladinoIdentity
from app.infrastructure.db.session import get_db
from app.modules.identity.schemas import ConsentRecordResponse, IdentityResponse
from app.modules.portal import auth_service, service
from app.modules.portal.schemas import (
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    PaymentSourceCreateRequest,
    PortalConsentRequest,
    PortalLoginRequest,
    PortalProfileUpdateRequest,
    PortalRegisterRequest,
    PortalTokenResponse,
)

router = APIRouter(prefix="/portal", tags=["portal"])


# ── Auth (público — sem JWT) ─────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
@limiter.limit("5/minute")
def register(request: Request, body: PortalRegisterRequest, db: Session = Depends(get_db)):
    return auth_service.register(
        db, email=body.email, name=body.name, phone=body.phone, password=body.password,
    )


@router.post("/auth/login", response_model=PortalTokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: PortalLoginRequest, db: Session = Depends(get_db)):
    token = auth_service.login_with_password(db, body.email, body.password)
    return {"access_token": token, "token_type": "bearer"}


@router.post("/auth/magic-link")
@limiter.limit("5/minute")
def magic_link(request: Request, body: MagicLinkRequest, db: Session = Depends(get_db)):
    """Sempre 200 — nunca revela se o e-mail existe."""
    auth_service.send_magic_link(db, body.email)
    return {"message": "Se o e-mail estiver cadastrado, você receberá o link em breve."}


@router.post("/auth/magic-link/verify", response_model=PortalTokenResponse)
@limiter.limit("10/minute")
def magic_link_verify(
    request: Request, body: MagicLinkVerifyRequest, db: Session = Depends(get_db)
):
    token = auth_service.verify_magic_link(db, body.token)
    return {"access_token": token, "token_type": "bearer"}


# ── Área logada ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
def dashboard(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.get_dashboard(db, identity.id)


@router.get("/history")
def history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    company_id: Optional[UUID] = Query(None),
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.get_history(db, identity.id, page=page, page_size=page_size, company_id=company_id)


@router.get("/credits")
def credits(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.get_credits(db, identity.id)


@router.get("/subscriptions")
def subscriptions(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.get_subscriptions(db, identity.id)


@router.post("/subscriptions/{subscription_id}/pause")
def pause_subscription(
    subscription_id: UUID,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.pause_subscription(db, identity.id, subscription_id)


@router.post("/subscriptions/{subscription_id}/cancel")
def cancel_subscription(
    subscription_id: UUID,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.cancel_subscription(db, identity.id, subscription_id)


@router.get("/consents", response_model=List[ConsentRecordResponse])
def list_consents(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.list_consents(db, identity.id)


@router.post("/consents/grant", response_model=ConsentRecordResponse, status_code=201)
def grant_consent(
    body: PortalConsentRequest,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.grant_consent(
        db, identity.id, body.consent_type, body.channel, company_id=body.company_id,
    )


@router.post("/consents/revoke", response_model=ConsentRecordResponse, status_code=201)
def revoke_consent(
    body: PortalConsentRequest,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.revoke_consent(
        db, identity.id, body.consent_type, body.channel, company_id=body.company_id,
    )


@router.get("/payment-sources")
def list_payment_sources(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.list_payment_sources(db, identity.id)


@router.post("/payment-sources", status_code=201)
def add_payment_source(
    body: PaymentSourceCreateRequest,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.add_payment_source(
        db, identity.id, body.company_id, body.source_token, body.mode,
        last_four=body.last_four, brand=body.brand,
    )


@router.delete("/payment-sources/{authorization_id}")
def revoke_payment_source(
    authorization_id: UUID,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.revoke_payment_source(db, identity.id, authorization_id)


@router.patch("/profile")
def update_profile(
    body: PortalProfileUpdateRequest,
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
    db: Session = Depends(get_db),
):
    return service.update_profile(
        db, identity, name=body.name, email=body.email, phone=body.phone,
    )


@router.get("/identity/me", response_model=IdentityResponse)
def identity_me(
    identity: PaladinoIdentity = Depends(get_current_portal_identity),
):
    """Dados da própria identity — resolve o 501 do Sprint A."""
    return identity
