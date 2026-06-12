from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.infrastructure.db.models.tenant_config import TenantConfig
from app.infrastructure.db.models.module_activation import ModuleActivation, ModuleName
from app.infrastructure.db.models.tenant_branding import TenantBranding
from app.infrastructure.db.models.user import User
from app.modules.tenant.schemas import TenantConfigUpdate, TenantBrandingUpdate


# ── TenantConfig ─────────────────────────────────────────────────────────────

def get_tenant_config_or_404(db: Session, company_id: UUID) -> TenantConfig:
    config = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
    if not config:
        raise HTTPException(status_code=404, detail="TenantConfig não encontrado")
    return config


def update_tenant_config(
    db: Session,
    company_id: UUID,
    data: TenantConfigUpdate,
    actor: User,
) -> TenantConfig:
    config = get_tenant_config_or_404(db, company_id)

    # Fail-fast antes do trigger do banco
    if data.accounting_mode and data.accounting_mode == "ACCRUAL":
        raise HTTPException(
            status_code=422,
            detail="accounting_mode ACCRUAL indisponível no Estágio 0",
        )

    before = {
        "timezone": config.timezone,
        "soft_reservation_ttl_min": config.soft_reservation_ttl_min,
        "draft_expiration_min": config.draft_expiration_min,
        "requested_expiration_h": config.requested_expiration_h,
        "no_show_threshold_min": config.no_show_threshold_min,
        "no_penalty_cancel_h": config.no_penalty_cancel_h,
        "require_payment_upfront": config.require_payment_upfront,
        "default_commission_pct": str(config.default_commission_pct),
        "accounting_mode": config.accounting_mode,
        "permission_overrides": config.permission_overrides,
    }

    updates = data.model_dump(exclude_none=True)
    # fee_routing_policy_id removido na migration l1m2n3o4p5q6 (Sprint 6)
    updates.pop("fee_routing_policy_id", None)

    for field, value in updates.items():
        setattr(config, field, value)

    config.updated_at = datetime.now(timezone.utc)

    after = {
        "timezone": config.timezone,
        "soft_reservation_ttl_min": config.soft_reservation_ttl_min,
        "draft_expiration_min": config.draft_expiration_min,
        "requested_expiration_h": config.requested_expiration_h,
        "no_show_threshold_min": config.no_show_threshold_min,
        "no_penalty_cancel_h": config.no_penalty_cancel_h,
        "require_payment_upfront": config.require_payment_upfront,
        "default_commission_pct": str(config.default_commission_pct),
        "accounting_mode": config.accounting_mode,
        "permission_overrides": config.permission_overrides,
    }

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor.id,
            actor_role=actor.role,
            action="update_config",
            resource_type="TenantConfig",
            resource_id=config.tenant_config_id,
            company_id=company_id,
            before_snapshot=before,
            after_snapshot=after,
        ),
        db,
    )

    db.commit()
    db.refresh(config)
    return config


def allows_subscription_pause(config: Optional[TenantConfig]) -> bool:
    """Tenant permite que o cliente pause a própria assinatura via Portal.

    Default False (opt-in via permission_overrides — Sprint D, B5).
    """
    if config is None:
        return False
    return bool((config.permission_overrides or {}).get("allow_subscription_pause", False))


def allows_subscription_cancel(config: Optional[TenantConfig]) -> bool:
    """Tenant permite que o cliente cancele a própria assinatura via Portal.

    Default True (opt-out via permission_overrides — Sprint D, B5).
    """
    if config is None:
        return True
    return bool((config.permission_overrides or {}).get("allow_subscription_cancel", True))


# ── ModuleActivation ─────────────────────────────────────────────────────────

def list_module_activations(db: Session, company_id: UUID) -> List[ModuleActivation]:
    return (
        db.query(ModuleActivation)
        .filter(ModuleActivation.company_id == company_id)
        .order_by(ModuleActivation.module_name)
        .all()
    )


def _get_module_or_404(db: Session, company_id: UUID, module_name: str) -> ModuleActivation:
    try:
        ModuleName(module_name)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Módulo '{module_name}' não existe")

    activation = (
        db.query(ModuleActivation)
        .filter(
            ModuleActivation.company_id == company_id,
            ModuleActivation.module_name == module_name,
        )
        .first()
    )
    if not activation:
        raise HTTPException(status_code=404, detail=f"Módulo '{module_name}' não encontrado")
    return activation


def activate_module(
    db: Session,
    company_id: UUID,
    module_name: str,
    actor: User,
) -> ModuleActivation:
    activation = _get_module_or_404(db, company_id, module_name)
    activation.is_active = True
    activation.activated_at = datetime.now(timezone.utc)
    activation.activated_by_user_id = actor.id
    activation.deactivated_at = None
    db.commit()
    db.refresh(activation)
    return activation


def deactivate_module(
    db: Session,
    company_id: UUID,
    module_name: str,
    actor: User,
) -> ModuleActivation:
    activation = _get_module_or_404(db, company_id, module_name)
    activation.is_active = False
    activation.deactivated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(activation)
    return activation


# ── TenantBranding ───────────────────────────────────────────────────────────

def get_branding_or_404(db: Session, company_id: UUID) -> TenantBranding:
    branding = (
        db.query(TenantBranding)
        .filter(TenantBranding.company_id == company_id)
        .first()
    )
    if not branding:
        raise HTTPException(status_code=404, detail="Branding não encontrado")
    return branding


def update_branding(
    db: Session,
    company_id: UUID,
    data: TenantBrandingUpdate,
) -> TenantBranding:
    branding = get_branding_or_404(db, company_id)

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(branding, field, value)

    from datetime import datetime, timezone
    branding.updated_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(branding)
    return branding
