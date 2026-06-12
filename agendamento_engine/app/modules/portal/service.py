"""
PortalService — Sprint D. Dados cross-tenant do cliente final.

Todas as queries partem do identity_id (PaladinoIdentity global) e chegam
aos dados tenant-scoped via customers.identity_id — o cliente vê os
PRÓPRIOS dados em TODOS os seus tenants; nenhum tenant enxerga outro.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Appointment,
    Customer,
    CustomerCredit,
    PaladinoIdentity,
    PaymentSourceAuthorization,
    PortalCredential,
    TenantConfig,
)
from app.infrastructure.db.models.subscription import CustomerSubscription
from app.modules.identity import consent_service
from app.modules.identity.consent_service import ConsentType, SourceChannel

logger = logging.getLogger(__name__)

HISTORY_STATUSES = ("COMPLETED", "CANCELLED", "NO_SHOW")
UPCOMING_STATUSES = ("SCHEDULED", "IN_PROGRESS")
PAYMENT_SOURCE_MODES = ("ALWAYS", "ONCE")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _customers_for_identity(db: Session, identity_id: UUID) -> list[Customer]:
    return (
        db.query(Customer)
        .filter(Customer.identity_id == identity_id, Customer.active == True)
        .all()
    )


def _customer_ids(customers: list[Customer]) -> list[UUID]:
    return [c.id for c in customers]


def _appointment_item(a: Appointment) -> dict:
    return {
        "id": str(a.id),
        "company_id": str(a.company_id),
        "start_at": a.start_at.isoformat(),
        "end_at": a.end_at.isoformat(),
        "status": a.status if isinstance(a.status, str) else a.status.value,
        "service_names": [s.service_name for s in a.services],
        "professional_name": a.professional.name if a.professional else None,
        "total_amount": str(a.total_amount),
    }


def _credit_item(c: CustomerCredit) -> dict:
    return {
        "credit_id": str(c.credit_id),
        "company_id": str(c.company_id),
        "entitlement_type": c.entitlement_type,
        "total_cotas": c.total_cotas,
        "remaining_cotas": c.remaining_cotas,
        "status": c.status,
        "granted_at": c.granted_at.isoformat() if c.granted_at else None,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
    }


def _subscription_item(s: CustomerSubscription) -> dict:
    return {
        "subscription_id": str(s.subscription_id),
        "company_id": str(s.company_id),
        "plan_name": s.plan.name if s.plan else None,
        "status": s.status,
        "next_billing_at": s.next_billing_at.isoformat() if s.next_billing_at else None,
        "paused_at": s.paused_at.isoformat() if s.paused_at else None,
        "cancelled_at": s.cancelled_at.isoformat() if s.cancelled_at else None,
    }


# ── Dashboard / History / Credits / Subscriptions ────────────────────────────

def get_dashboard(db: Session, identity_id: UUID) -> dict:
    """Próximos agendamentos, cotas e assinaturas ativas — cross-tenant."""
    customers = _customers_for_identity(db, identity_id)
    customer_ids = _customer_ids(customers)
    if not customer_ids:
        return {
            "upcoming_appointments": [],
            "active_credits": [],
            "active_subscriptions": [],
        }

    now = datetime.now(timezone.utc)
    upcoming = (
        db.query(Appointment)
        .filter(
            Appointment.client_id.in_(customer_ids),
            Appointment.status.in_(UPCOMING_STATUSES),
            Appointment.start_at >= now,
        )
        .order_by(Appointment.start_at.asc())
        .all()
    )
    credits = (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.customer_id.in_(customer_ids),
            CustomerCredit.status == "ACTIVE",
        )
        .all()
    )
    subscriptions = (
        db.query(CustomerSubscription)
        .filter(
            CustomerSubscription.customer_id.in_(customer_ids),
            CustomerSubscription.status.in_(("ACTIVE", "PAUSED", "OVERDUE")),
        )
        .all()
    )
    return {
        "upcoming_appointments": [_appointment_item(a) for a in upcoming],
        "active_credits": [_credit_item(c) for c in credits],
        "active_subscriptions": [_subscription_item(s) for s in subscriptions],
    }


def get_history(
    db: Session,
    identity_id: UUID,
    page: int = 1,
    page_size: int = 20,
    company_id: Optional[UUID] = None,
) -> dict:
    """Appointments históricos (COMPLETED/CANCELLED/NO_SHOW), paginados."""
    customers = _customers_for_identity(db, identity_id)
    if company_id is not None:
        customers = [c for c in customers if c.company_id == company_id]
    customer_ids = _customer_ids(customers)
    if not customer_ids:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

    query = db.query(Appointment).filter(
        Appointment.client_id.in_(customer_ids),
        Appointment.status.in_(HISTORY_STATUSES),
    )
    total = query.count()
    items = (
        query.order_by(Appointment.start_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_appointment_item(a) for a in items],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def get_credits(db: Session, identity_id: UUID) -> list[dict]:
    """CustomerCredits ativos, FEFO (expires_at asc, sem expiração por último)."""
    customer_ids = _customer_ids(_customers_for_identity(db, identity_id))
    if not customer_ids:
        return []
    credits = (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.customer_id.in_(customer_ids),
            CustomerCredit.status == "ACTIVE",
        )
        .all()
    )
    # FEFO: expires_at mais próximo primeiro; sem expiração → final
    credits.sort(key=lambda c: (c.expires_at is None, c.expires_at or datetime.max.replace(tzinfo=timezone.utc)))
    return [_credit_item(c) for c in credits]


def get_subscriptions(db: Session, identity_id: UUID) -> list[dict]:
    """CustomerSubscriptions ativas/pausadas/em atraso — cross-tenant."""
    customer_ids = _customer_ids(_customers_for_identity(db, identity_id))
    if not customer_ids:
        return []
    subscriptions = (
        db.query(CustomerSubscription)
        .filter(
            CustomerSubscription.customer_id.in_(customer_ids),
            CustomerSubscription.status.in_(("ACTIVE", "PAUSED", "OVERDUE")),
        )
        .all()
    )
    return [_subscription_item(s) for s in subscriptions]


def _get_owned_subscription(
    db: Session, identity_id: UUID, subscription_id: UUID
) -> CustomerSubscription:
    """Subscription pertencente à identity (via customer) ou 404."""
    sub = (
        db.query(CustomerSubscription)
        .filter(CustomerSubscription.subscription_id == subscription_id)
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")
    customer = db.query(Customer).filter(Customer.id == sub.customer_id).first()
    if not customer or customer.identity_id != identity_id:
        raise HTTPException(status_code=404, detail="Assinatura não encontrada")
    return sub


def _tenant_config(db: Session, company_id: UUID) -> Optional[TenantConfig]:
    return db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()


def pause_subscription(db: Session, identity_id: UUID, subscription_id: UUID) -> dict:
    """Pausa a própria assinatura — 403 se o tenant não permite."""
    from app.modules.subscriptions import service as subscription_svc
    from app.modules.tenant.service import allows_subscription_pause

    sub = _get_owned_subscription(db, identity_id, subscription_id)
    if not allows_subscription_pause(_tenant_config(db, sub.company_id)):
        raise HTTPException(
            status_code=403,
            detail="Este estabelecimento não permite pausar assinaturas pelo Portal",
        )
    sub = subscription_svc.pause(sub.subscription_id, sub.company_id, db)
    return _subscription_item(sub)


def cancel_subscription(db: Session, identity_id: UUID, subscription_id: UUID) -> dict:
    """Cancela a própria assinatura — 403 se o tenant não permite."""
    from app.modules.subscriptions import service as subscription_svc
    from app.modules.tenant.service import allows_subscription_cancel

    sub = _get_owned_subscription(db, identity_id, subscription_id)
    if not allows_subscription_cancel(_tenant_config(db, sub.company_id)):
        raise HTTPException(
            status_code=403,
            detail="Este estabelecimento não permite cancelar assinaturas pelo Portal",
        )
    sub = subscription_svc.cancel(sub.subscription_id, sub.company_id, db)
    return _subscription_item(sub)


# ── Consents ──────────────────────────────────────────────────────────────────

def list_consents(db: Session, identity_id: UUID) -> list:
    """Estado vigente de consents da identity (todos os tenants + globais)."""
    return consent_service.get_consents_for_identity(db, identity_id, None)


def grant_consent(
    db: Session,
    identity_id: UUID,
    consent_type: str,
    channel: Optional[str],
    company_id: Optional[UUID] = None,
):
    return consent_service.grant_consent(
        db, identity_id, company_id, consent_type, channel, SourceChannel.PORTAL,
    )


def revoke_consent(
    db: Session,
    identity_id: UUID,
    consent_type: str,
    channel: Optional[str],
    company_id: Optional[UUID] = None,
):
    return consent_service.revoke_consent(
        db, identity_id, company_id, consent_type, channel, SourceChannel.PORTAL,
    )


# ── Payment sources ───────────────────────────────────────────────────────────

def _payment_source_item(p: PaymentSourceAuthorization) -> dict:
    return {
        "id": str(p.id),
        "company_id": str(p.company_id),
        "provider": p.provider,
        "mode": p.mode,
        "last_four": p.last_four,
        "brand": p.brand,
        "granted_at": p.granted_at.isoformat() if p.granted_at else None,
        "revoked_at": p.revoked_at.isoformat() if p.revoked_at else None,
    }


def list_payment_sources(db: Session, identity_id: UUID) -> list[dict]:
    sources = (
        db.query(PaymentSourceAuthorization)
        .filter(
            PaymentSourceAuthorization.identity_id == identity_id,
            PaymentSourceAuthorization.revoked_at.is_(None),
        )
        .all()
    )
    return [_payment_source_item(p) for p in sources]


def add_payment_source(
    db: Session,
    identity_id: UUID,
    company_id: UUID,
    source_token: str,
    mode: str,
    last_four: Optional[str] = None,
    brand: Optional[str] = None,
    provider: str = "ASAAS",
) -> dict:
    """Autoriza fonte de pagamento para um tenant.

    Exige consent PAYMENT_STORAGE vigente para o tenant → 422 sem ele.
    """
    mode = (mode or "").upper()
    if mode not in PAYMENT_SOURCE_MODES:
        raise HTTPException(
            status_code=422,
            detail=f"mode inválido — use um de: {', '.join(PAYMENT_SOURCE_MODES)}",
        )

    has_consent = consent_service.check_consent(
        db, identity_id, company_id, ConsentType.PAYMENT_STORAGE, None,
    )
    if not has_consent:
        raise HTTPException(
            status_code=422,
            detail="Consent PAYMENT_STORAGE necessário para salvar método de pagamento",
        )

    authorization = PaymentSourceAuthorization(
        identity_id=identity_id,
        company_id=company_id,
        source_token=source_token,
        provider=provider,
        mode=mode,
        last_four=last_four,
        brand=brand,
    )
    db.add(authorization)
    db.commit()
    return _payment_source_item(authorization)


def revoke_payment_source(db: Session, identity_id: UUID, authorization_id: UUID) -> dict:
    auth = (
        db.query(PaymentSourceAuthorization)
        .filter(PaymentSourceAuthorization.id == authorization_id)
        .first()
    )
    if not auth or auth.identity_id != identity_id:
        raise HTTPException(status_code=404, detail="Fonte de pagamento não encontrada")
    if auth.revoked_at is None:
        auth.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return _payment_source_item(auth)


# ── Profile ───────────────────────────────────────────────────────────────────

def update_profile(
    db: Session,
    identity: PaladinoIdentity,
    name: Optional[str] = None,
    email: Optional[str] = None,
    phone: Optional[str] = None,
) -> dict:
    """
    name  → atualiza direto na identity.
    phone → re-resolve: se o E.164 novo já pertence a OUTRA identity → 409
            (merge de identidades é operação manual, fora do escopo).
    email → atualiza portal_credentials com email_verified=False e envia
            verificação (obrigatória) por magic link.
    """
    from app.modules.identity.resolver import normalize_phone_e164
    from app.modules.portal import auth_service

    email_verification_sent = False

    if name is not None:
        identity.name = name

    if phone is not None:
        phone_e164, phone_national = normalize_phone_e164(phone)  # 422 sem DDD
        if phone_e164 != identity.phone_e164:
            other = (
                db.query(PaladinoIdentity)
                .filter(PaladinoIdentity.phone_e164 == phone_e164)
                .first()
            )
            if other and other.id != identity.id:
                raise HTTPException(
                    status_code=409,
                    detail="Telefone já vinculado a outra conta Paladino",
                )
            identity.phone_e164 = phone_e164
            identity.phone_national_normalized = phone_national

    if email is not None:
        email = email.strip().lower()
        credential = (
            db.query(PortalCredential)
            .filter(PortalCredential.identity_id == identity.id)
            .first()
        )
        if credential and email != credential.email:
            taken = (
                db.query(PortalCredential)
                .filter(PortalCredential.email == email)
                .first()
            )
            if taken:
                raise HTTPException(status_code=409, detail="E-mail já cadastrado no Portal")
            credential.email = email
            credential.email_verified = False
            identity.email = email
            db.commit()
            try:
                auth_service._issue_and_send_magic_link(
                    db, identity.id, email,
                    subject="Confirme seu novo e-mail — Portal Paladino",
                    intro="Confirme seu novo e-mail acessando o link:",
                )
                email_verification_sent = True
            except Exception:
                logger.exception("update_profile: falha ao enviar verificação para %s", email)

    db.commit()

    return {
        "identity_id": str(identity.id),
        "name": identity.name,
        "email": identity.email,
        "phone_e164": identity.phone_e164,
        "email_verification_sent": email_verification_sent,
    }
