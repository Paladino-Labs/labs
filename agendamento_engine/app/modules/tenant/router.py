from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role, get_current_company_id, get_current_user
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.user import User
from app.modules.tenant import schemas, service

router = APIRouter(prefix="/tenant", tags=["tenant"])

_owner_admin = require_role("OWNER", "ADMIN", "PLATFORM_OWNER")
_owner_admin_operator = require_role("OWNER", "ADMIN", "OPERATOR", "PLATFORM_OWNER")


# ── TenantConfig ─────────────────────────────────────────────────────────────

@router.get("/config", response_model=schemas.TenantConfigResponse)
def get_tenant_config(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    return service.get_tenant_config_or_404(db, company_id)


@router.put("/config", response_model=schemas.TenantConfigResponse)
def update_tenant_config(
    body: schemas.TenantConfigUpdate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.update_tenant_config(db, company_id, body, actor)


# ── ModuleActivation ─────────────────────────────────────────────────────────

@router.get("/modules", response_model=List[schemas.ModuleActivationResponse])
def list_modules(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    return service.list_module_activations(db, company_id)


@router.post("/modules/{module_name}/activate", response_model=schemas.ModuleActivationResponse)
def activate_module(
    module_name: str,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.activate_module(db, company_id, module_name.upper(), actor)


@router.post("/modules/{module_name}/deactivate", response_model=schemas.ModuleActivationResponse)
def deactivate_module(
    module_name: str,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.deactivate_module(db, company_id, module_name.upper(), actor)


# ── TenantBranding ───────────────────────────────────────────────────────────

@router.get("/branding", response_model=schemas.TenantBrandingResponse)
def get_branding(
    company_id: UUID = Query(..., description="ID da empresa (público — sem auth obrigatória)"),
    db: Session = Depends(get_db),
):
    """Público — retorna branding sem autenticação. Usado pelo Link Público."""
    return service.get_branding_or_404(db, company_id)


@router.put("/branding", response_model=schemas.TenantBrandingResponse)
def update_branding(
    body: schemas.TenantBrandingUpdate,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin),
    db: Session = Depends(get_db),
):
    return service.update_branding(db, company_id, body)
