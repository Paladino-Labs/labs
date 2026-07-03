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
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Appointment,
    Company,
    CompanyProfile,
    Coupon,
    Customer,
    CustomerCredit,
    CustomerCreditConsumption,
    Package,
    PackagePurchase,
    PaladinoIdentity,
    Payment,
    PaymentSourceAuthorization,
    PortalCredential,
    Product,
    Promotion,
    Service,
    TenantConfig,
)
from app.infrastructure.db.models.subscription import CustomerSubscription, SubscriptionPlan
from app.modules.identity import consent_service
from app.modules.identity.consent_service import ConsentType, SourceChannel

logger = logging.getLogger(__name__)

HISTORY_STATUSES = ("COMPLETED", "CANCELLED", "NO_SHOW")
UPCOMING_STATUSES = ("SCHEDULED", "IN_PROGRESS")
PAYMENT_SOURCE_MODES = ("ALWAYS", "ONCE")
# Universo de status operacionais de Appointment (B4 — validação do filtro).
VALID_APPOINTMENT_STATUSES = (
    "SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW",
)
# B2 — rótulos legíveis quando o crédito não resolve um serviço específico.
# CustomerCredit não tem FK service_id; o serviço (quando existe) vem da origem.
_ENTITLEMENT_LABELS = {
    "PACKAGE": "Pacote",
    "SUBSCRIPTION": "Assinatura",
    "GRANT_COTA": "Cota cortesia",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _customers_for_identity(db: Session, identity_id: UUID) -> list[Customer]:
    return (
        db.query(Customer)
        .filter(Customer.identity_id == identity_id, Customer.active == True)
        .all()
    )


def _customer_ids(customers: list[Customer]) -> list[UUID]:
    return [c.id for c in customers]


def _company_names(db: Session, company_ids) -> dict:
    """Lookup em batch company_id → Company.name (B1). Evita N+1."""
    ids = {cid for cid in company_ids if cid is not None}
    if not ids:
        return {}
    rows = db.query(Company).filter(Company.id.in_(ids)).all()
    return {c.id: c.name for c in rows}


def _entitlement_label(entitlement_type) -> Optional[str]:
    if not entitlement_type:
        return None
    if entitlement_type in _ENTITLEMENT_LABELS:
        return _ENTITLEMENT_LABELS[entitlement_type]
    return entitlement_type.replace("_", " ").capitalize()


def _resolve_credit_service_name(db: Session, credit) -> Optional[str]:
    """Nome legível para o crédito.

    Sprint 26: CustomerCredit tem FK service_id/product_id direto. Resolve o
    nome do serviço (ou produto); na ausência de ambos (cota genérica /
    GRANT_COTA) cai no rótulo legível do entitlement_type. Best-effort:
    nunca levanta — a UI sempre recebe algo exibível.
    """
    try:
        if getattr(credit, "service_id", None):
            service = db.query(Service).filter(Service.id == credit.service_id).first()
            if service and getattr(service, "name", None):
                return service.name
        if getattr(credit, "product_id", None):
            product = db.query(Product).filter(Product.id == credit.product_id).first()
            if product and getattr(product, "name", None):
                return product.name
    except Exception:
        logger.debug("resolve_credit_service_name falhou", exc_info=True)
    return _entitlement_label(getattr(credit, "entitlement_type", None))


def _appointment_item(a: Appointment, company_name: Optional[str] = None) -> dict:
    return {
        "id": str(a.id),
        "company_id": str(a.company_id),
        "company_name": company_name,
        "start_at": a.start_at.isoformat(),
        "end_at": a.end_at.isoformat(),
        "status": a.status if isinstance(a.status, str) else a.status.value,
        "service_names": [s.service_name for s in a.services],
        "professional_name": a.professional.name if a.professional else None,
        "total_amount": str(a.total_amount),
    }


def _credit_item(
    c: CustomerCredit,
    company_name: Optional[str] = None,
    service_name: Optional[str] = None,
) -> dict:
    return {
        "credit_id": str(c.credit_id),
        "company_id": str(c.company_id),
        "company_name": company_name,
        "entitlement_type": c.entitlement_type,
        "service_name": service_name,
        "total_cotas": c.total_cotas,
        "remaining_cotas": c.remaining_cotas,
        "status": c.status,
        "granted_at": c.granted_at.isoformat() if c.granted_at else None,
        "expires_at": c.expires_at.isoformat() if c.expires_at else None,
    }


def _subscription_item(s: CustomerSubscription, company_name: Optional[str] = None) -> dict:
    return {
        "subscription_id": str(s.subscription_id),
        "company_id": str(s.company_id),
        "company_name": company_name,
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
    names = _company_names(
        db,
        [a.company_id for a in upcoming]
        + [c.company_id for c in credits]
        + [s.company_id for s in subscriptions],
    )
    return {
        "upcoming_appointments": [
            _appointment_item(a, names.get(a.company_id)) for a in upcoming
        ],
        "active_credits": [
            _credit_item(
                c, names.get(c.company_id), _resolve_credit_service_name(db, c)
            )
            for c in credits
        ],
        "active_subscriptions": [
            _subscription_item(s, names.get(s.company_id)) for s in subscriptions
        ],
    }


def get_history(
    db: Session,
    identity_id: UUID,
    page: int = 1,
    page_size: int = 20,
    company_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> dict:
    """Appointments históricos (COMPLETED/CANCELLED/NO_SHOW), paginados.

    B4 — `status` opcional filtra dentro do histórico. Status fora do universo
    de Appointment → 422; status válido mas não-histórico (ex: SCHEDULED) →
    lista vazia (não há interseção com o histórico).
    """
    if status is not None:
        status = status.upper()
        if status not in VALID_APPOINTMENT_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=(
                    "status inválido — use um de: "
                    + ", ".join(VALID_APPOINTMENT_STATUSES)
                ),
            )

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
    if status is not None:
        query = query.filter(Appointment.status == status)
    total = query.count()
    items = (
        query.order_by(Appointment.start_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    names = _company_names(db, [a.company_id for a in items])
    return {
        "items": [_appointment_item(a, names.get(a.company_id)) for a in items],
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
    names = _company_names(db, [c.company_id for c in credits])
    return [
        _credit_item(c, names.get(c.company_id), _resolve_credit_service_name(db, c))
        for c in credits
    ]


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
    names = _company_names(db, [s.company_id for s in subscriptions])
    return [_subscription_item(s, names.get(s.company_id)) for s in subscriptions]


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
    return _subscription_item(sub, _company_names(db, [sub.company_id]).get(sub.company_id))


def resume_subscription(db: Session, identity_id: UUID, subscription_id: UUID) -> dict:
    """Retoma a própria assinatura (PAUSED → ACTIVE) — B5.

    Reusa o mesmo gate de pause: se o tenant permite pausar pelo Portal,
    permite retomar (pausar/retomar é a mesma capacidade). `resume` do
    tenant valida a transição (422 se a assinatura não está PAUSED).
    """
    from app.modules.subscriptions import service as subscription_svc
    from app.modules.tenant.service import allows_subscription_pause

    sub = _get_owned_subscription(db, identity_id, subscription_id)
    if not allows_subscription_pause(_tenant_config(db, sub.company_id)):
        raise HTTPException(
            status_code=403,
            detail="Este estabelecimento não permite gerenciar pausas pelo Portal",
        )
    sub = subscription_svc.resume(sub.subscription_id, sub.company_id, db)
    return _subscription_item(sub, _company_names(db, [sub.company_id]).get(sub.company_id))


# ── Companies / Coupons / Payments (Portal Camada 2) ─────────────────────────

def get_companies(db: Session, identity_id: UUID) -> list[dict]:
    """Empresas onde a identity tem Customer ativo (cross-tenant).

    O slug é essencial — o frontend monta o link "Agendar" (/book/{slug}).
    """
    customers = _customers_for_identity(db, identity_id)
    company_ids = list({c.company_id for c in customers})
    if not company_ids:
        return []

    companies = (
        db.query(Company)
        .filter(Company.id.in_(company_ids))
        .all()
    )
    # CompanyProfile 1:1 para logo/endereço
    profiles = (
        db.query(CompanyProfile)
        .filter(CompanyProfile.company_id.in_(company_ids))
        .all()
    )
    profile_by_company = {p.company_id: p for p in profiles}

    result = []
    for company in companies:
        profile = profile_by_company.get(company.id)
        result.append({
            "company_id":   str(company.id),
            "company_name": company.name,
            "slug":         company.slug,
            "logo_url":     profile.logo_url if profile else None,
            "address":      profile.address if profile else None,
            "city":         profile.city if profile else None,
        })
    return result


def get_coupons(db: Session, identity_id: UUID) -> list[dict]:
    """Cupons ativos: nominais da identity + genéricos das empresas dela.

    Coupon não tem discount_type/discount_value próprios — vêm da Promotion
    pai (promotion_id). Vigência do cupom é `expires_at` (fallback:
    valid_until da promoção).
    """
    customers = _customers_for_identity(db, identity_id)
    customer_ids = [c.id for c in customers]
    company_ids = list({c.company_id for c in customers})
    if not company_ids:
        return []

    now = datetime.now(timezone.utc)
    # Cupons nominais (customer_id da identity) OU genéricos do tenant
    # (customer_id NULL) — ambos ACTIVE e vigentes
    coupons = (
        db.query(Coupon)
        .filter(
            Coupon.company_id.in_(company_ids),
            Coupon.status == "ACTIVE",
            or_(
                Coupon.customer_id.in_(customer_ids),
                Coupon.customer_id.is_(None),
            ),
        )
        .all()
    )
    company_names = _company_names(db, company_ids)
    promotion_ids = {c.promotion_id for c in coupons if c.promotion_id}
    promotions = (
        db.query(Promotion).filter(Promotion.id.in_(promotion_ids)).all()
        if promotion_ids else []
    )
    promo_by_id = {p.id: p for p in promotions}

    result = []
    for c in coupons:
        promo = promo_by_id.get(c.promotion_id)
        valid_until = c.expires_at or (promo.valid_until if promo else None)
        if valid_until:
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=timezone.utc)
            if valid_until < now:
                continue
        result.append({
            "coupon_id":      str(c.id),
            "code":           c.code,
            "company_name":   company_names.get(c.company_id, ""),
            "discount_type":  promo.discount_type if promo else None,
            "discount_value": (
                str(promo.discount_value)
                if promo and promo.discount_value is not None else None
            ),
            "valid_until":    valid_until.isoformat() if valid_until else None,
            "is_personal":    c.customer_id is not None,
        })
    return result


def get_payments(db: Session, identity_id: UUID,
                 page: int = 1, page_size: int = 20) -> dict:
    """Histórico de pagamentos da identity (via customers), paginado."""
    customers = _customers_for_identity(db, identity_id)
    customer_ids = [c.id for c in customers]
    if not customer_ids:
        return {"items": [], "page": page, "page_size": page_size, "total": 0}

    base = (
        db.query(Payment)
        .filter(Payment.customer_id.in_(customer_ids))
        .order_by(Payment.created_at.desc())
    )
    total = base.count()
    payments = base.offset((page - 1) * page_size).limit(page_size).all()

    company_ids = list({c.company_id for c in customers})
    company_names = _company_names(db, company_ids)
    # customer → company para exibir o nome
    company_by_customer = {c.id: c.company_id for c in customers}

    items = []
    for p in payments:
        company_id = company_by_customer.get(p.customer_id)
        items.append({
            "payment_id":     str(p.payment_id),
            "company_name":   company_names.get(company_id, ""),
            "amount":         str(p.net_charged_amount),
            "payment_method": p.payment_method,
            "status":         p.status,
            "paid_at":        p.paid_at.isoformat() if p.paid_at else None,
            "created_at":     p.created_at.isoformat() if p.created_at else None,
            "coupon_code":    p.coupon_code,
        })
    return {"items": items, "page": page, "page_size": page_size, "total": total}


# ── Appointments (detalhe + cancelar/remarcar) ────────────────────────────────

def _get_owned_appointment(
    db: Session, identity_id: UUID, appointment_id: UUID
) -> Appointment:
    """Appointment da identity (via customer) ou 404 genérico."""
    appt = (
        db.query(Appointment)
        .filter(Appointment.id == appointment_id)
        .first()
    )
    if not appt:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    customer = db.query(Customer).filter(Customer.id == appt.client_id).first()
    if not customer or customer.identity_id != identity_id:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return appt


def get_appointment_detail(db: Session, identity_id: UUID,
                           appointment_id: UUID) -> dict:
    """Detalhe rico de um agendamento — endereço, serviços e can_cancel/can_reschedule."""
    appt = _get_owned_appointment(db, identity_id, appointment_id)

    company = db.query(Company).filter(Company.id == appt.company_id).first()
    profile = (
        db.query(CompanyProfile)
        .filter(CompanyProfile.company_id == appt.company_id)
        .first()
    )
    services = [
        {"service_name": s.service_name,
         "duration_minutes": int(s.duration_snapshot),
         "price": str(s.price_snapshot)}
        for s in appt.services
    ]
    is_scheduled = appt.status == "SCHEDULED"

    return {
        "appointment_id":    str(appt.id),
        "company_name":      company.name if company else "",
        "company_address":   profile.address if profile else None,
        "company_city":      profile.city if profile else None,
        "company_maps_url":  profile.maps_url if profile else None,
        "company_whatsapp":  profile.whatsapp if profile else None,
        "company_timezone":  company.timezone if company else "America/Sao_Paulo",
        "professional_name": appt.professional.name if appt.professional else None,
        "services":          services,
        "start_at":          appt.start_at.isoformat(),
        "end_at":            appt.end_at.isoformat(),
        "status":            appt.status,
        "total_amount":      str(appt.total_amount),
        "can_cancel":        is_scheduled,
        "can_reschedule":    is_scheduled,
    }


def _compute_deposit_retained(db: Session, appointment: Appointment) -> bool:
    """
    Informa se o sinal SERÁ retido no cancelamento (fora da janela de
    reembolso). Computado ANTES do cancel (depois o Payment vira REFUNDED
    e a query não acharia). Mesmo flag que o /manage produz, via primitivas
    do deposit_service: sem política ou sem sinal CONFIRMED → False.
    """
    from app.modules.payments.deposit_service import (
        resolve_deposit_policy, is_within_refund_window,
    )
    service_id = appointment.services[0].service_id if appointment.services else None
    policy = resolve_deposit_policy(service_id, appointment.company_id, db)
    if policy is None:
        return False

    deposit_paid = (
        db.query(Payment)
        .filter(
            Payment.company_id == appointment.company_id,
            Payment.appointment_id == appointment.id,
            Payment.status == "CONFIRMED",
        )
        .first()
    )
    if deposit_paid is None:
        return False

    start_at = appointment.start_at
    if start_at.tzinfo is None:
        start_at = start_at.replace(tzinfo=timezone.utc)
    within = is_within_refund_window(
        start_at, datetime.now(timezone.utc), policy.refundable_until_hours_before,
    )
    return not within


# ── Credit consumptions (B3) ──────────────────────────────────────────────────

def get_credit_consumptions(db: Session, identity_id: UUID, credit_id: UUID) -> list[dict]:
    """Histórico de consumo de uma cota — B3.

    404 se o crédito não existe ou não pertence à identity logada. Cada
    consumo equivale a 1 cota (consume_for_operation decrementa de 1 em 1).
    service_name/professional_name vêm do appointment vinculado (quando há).
    """
    credit = (
        db.query(CustomerCredit)
        .filter(CustomerCredit.credit_id == credit_id)
        .first()
    )
    if not credit:
        raise HTTPException(status_code=404, detail="Crédito não encontrado")
    customer = db.query(Customer).filter(Customer.id == credit.customer_id).first()
    if not customer or customer.identity_id != identity_id:
        raise HTTPException(status_code=404, detail="Crédito não encontrado")

    consumptions = (
        db.query(CustomerCreditConsumption)
        .filter(CustomerCreditConsumption.credit_id == credit_id)
        .order_by(CustomerCreditConsumption.consumed_at.desc())
        .all()
    )

    items: list[dict] = []
    for c in consumptions:
        service_name = None
        professional_name = None
        if c.appointment_id is not None:
            appt = (
                db.query(Appointment)
                .filter(Appointment.id == c.appointment_id)
                .first()
            )
            if appt is not None:
                svcs = getattr(appt, "services", None) or []
                service_name = svcs[0].service_name if svcs else None
                professional_name = appt.professional.name if appt.professional else None
        items.append({
            "occurred_at": c.consumed_at.isoformat() if c.consumed_at else None,
            "appointment_id": str(c.appointment_id) if c.appointment_id else None,
            "service_name": service_name,
            "professional_name": professional_name,
            "quantity_used": 1,
        })
    return items


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
