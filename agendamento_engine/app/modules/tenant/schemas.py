from decimal import Decimal
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, Field


# ── TenantConfig ─────────────────────────────────────────────────────────────

class TenantConfigResponse(BaseModel):
    tenant_config_id: UUID
    company_id: UUID
    timezone: str
    soft_reservation_ttl_min: int
    draft_expiration_min: int
    requested_expiration_h: int
    no_show_threshold_min: int
    no_penalty_cancel_h: int
    require_payment_upfront: bool
    default_commission_pct: Decimal
    fee_routing_policy_id: Optional[UUID]
    accounting_mode: str
    permission_overrides: dict

    model_config = {"from_attributes": True}


class TenantConfigUpdate(BaseModel):
    timezone: Optional[str] = Field(None, min_length=1, max_length=50)
    soft_reservation_ttl_min: Optional[int] = Field(None, ge=1, le=120)
    draft_expiration_min: Optional[int] = Field(None, ge=1, le=1440)
    requested_expiration_h: Optional[int] = Field(None, ge=1, le=168)
    no_show_threshold_min: Optional[int] = Field(None, ge=0, le=180)
    no_penalty_cancel_h: Optional[int] = Field(None, ge=0, le=168)
    require_payment_upfront: Optional[bool] = None
    default_commission_pct: Optional[Decimal] = Field(None, ge=0, le=100)
    accounting_mode: Optional[str] = None
    permission_overrides: Optional[dict] = None
    # fee_routing_policy_id é read-only neste endpoint — gerenciado pelo Financial Core


# ── ModuleActivation ─────────────────────────────────────────────────────────

class ModuleActivationResponse(BaseModel):
    activation_id: UUID
    company_id: UUID
    module_name: str
    is_active: bool

    model_config = {"from_attributes": True}


# ── TenantBranding ───────────────────────────────────────────────────────────

class TenantBrandingResponse(BaseModel):
    branding_id: UUID
    company_id: UUID
    logo_url: Optional[str]
    primary_color: Optional[str]
    secondary_color: Optional[str]
    font_family: Optional[str]
    favicon_url: Optional[str]
    custom_texts: dict

    model_config = {"from_attributes": True}


class TenantBrandingUpdate(BaseModel):
    logo_url: Optional[str] = None
    primary_color: Optional[str] = Field(None, max_length=7)
    secondary_color: Optional[str] = Field(None, max_length=7)
    font_family: Optional[str] = None
    favicon_url: Optional[str] = None
    custom_texts: Optional[dict] = None
