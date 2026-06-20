from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import require_role, get_current_user, get_current_company_id
from app.core.audit.sensitive_context import ActionScope
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models import User, Customer
from app.infrastructure.db.models.communication_setting import CommunicationSetting
from app.infrastructure.db.models.communication_template import CommunicationTemplate
from app.infrastructure.db.models.communication_log import CommunicationLog
from app.modules.communication.schemas import (
    CommunicationSettingsResponse,
    CommunicationSettingsUpdate,
    TemplateCreate,
    TemplateUpdate,
    TemplateResponse,
    CommunicationLogResponse,
)

router = APIRouter(prefix="/communication", tags=["communication"])


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings", response_model=CommunicationSettingsResponse)
def get_settings(
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    s = db.query(CommunicationSetting).filter(
        CommunicationSetting.company_id == company_id
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Configurações de comunicação não encontradas")
    return s


@router.put("/settings", response_model=CommunicationSettingsResponse)
def update_settings(
    body: CommunicationSettingsUpdate,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    s = db.query(CommunicationSetting).filter(
        CommunicationSetting.company_id == company_id
    ).first()
    if not s:
        raise HTTPException(status_code=404, detail="Configurações de comunicação não encontradas")

    data = body.model_dump(exclude_none=True)
    for field, val in data.items():
        if field in ("quiet_hours_start", "quiet_hours_end"):
            from datetime import time as dtime
            h, m = val.split(":")
            val = dtime(int(h), int(m))
        setattr(s, field, val)
    s.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(s)
    return s


# ── Templates ─────────────────────────────────────────────────────────────────

@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(
    user: User = Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    return (
        db.query(CommunicationTemplate)
        .filter(CommunicationTemplate.company_id == company_id)
        .all()
    )


@router.post("/templates", response_model=TemplateResponse, status_code=201)
def create_template(
    body: TemplateCreate,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    tmpl = CommunicationTemplate(
        company_id=company_id,
        event_type=body.event_type,
        channel=body.channel,
        audience=body.audience,
        body_template=body.body_template,
        is_active=body.is_active,
        is_default=body.is_default,
    )
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.put("/templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID,
    body: TemplateUpdate,
    user: User = Depends(get_current_user),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    tmpl = _get_template_or_404(db, company_id, template_id)

    # OPERATOR pode editar templates não-default se tiver override
    if user.role == "OPERATOR":
        overrides = _get_permission_overrides(db, company_id)
        if not overrides.get("OPERATOR", {}).get("update_operational_templates"):
            raise HTTPException(status_code=403, detail="OPERATOR sem permissão para editar templates")
        if tmpl.is_default:
            raise HTTPException(status_code=403, detail="OPERATOR não pode editar templates padrão")
    elif user.role not in ("OWNER", "ADMIN", "PLATFORM_OWNER"):
        raise HTTPException(status_code=403, detail="Sem permissão para editar templates")

    data = body.model_dump(exclude_none=True)
    for field, val in data.items():
        setattr(tmpl, field, val)
    db.commit()
    db.refresh(tmpl)
    return tmpl


@router.delete("/templates/{template_id}", status_code=204)
def delete_template(
    template_id: UUID,
    user: User = Depends(require_role("OWNER", "ADMIN")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    tmpl = _get_template_or_404(db, company_id, template_id)
    if tmpl.is_default:
        raise HTTPException(
            status_code=422,
            detail="Templates padrão não podem ser removidos — apenas desativados via PUT.",
        )
    db.delete(tmpl)
    db.commit()


# ── Logs ──────────────────────────────────────────────────────────────────────

@router.get("/logs", response_model=list[CommunicationLogResponse])
def list_logs(
    event_type: str | None = Query(None),
    status: str | None = Query(None),
    channel: str | None = Query(None),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(require_role("OWNER", "ADMIN", "OPERATOR")),
    company_id: UUID = Depends(get_current_company_id),
    db: Session = Depends(get_db),
):
    q = db.query(CommunicationLog).filter(CommunicationLog.company_id == company_id)
    if event_type:
        q = q.filter(CommunicationLog.event_type == event_type)
    if status:
        q = q.filter(CommunicationLog.status == status)
    if channel:
        q = q.filter(CommunicationLog.channel == channel)
    if date_from:
        q = q.filter(CommunicationLog.created_at >= date_from)
    if date_to:
        q = q.filter(CommunicationLog.created_at <= date_to)
    q = q.order_by(CommunicationLog.created_at.desc())
    logs = q.offset((page - 1) * limit).limit(limit).all()

    # Resolve o nome do destinatário em lote (sem N+1). recipient_type não é
    # confiável (ex.: auth.password_reset_requested usa CLIENT mas recipient_id
    # é um User), então procuramos em ambas as tabelas: Customer primeiro
    # (escopo da empresa), User para os ids restantes.
    all_ids = {l.recipient_id for l in logs}
    names: dict[UUID, str] = {}
    kinds: dict[UUID, str] = {}
    if all_ids:
        for cid, cname in (
            db.query(Customer.id, Customer.name)
            .filter(Customer.company_id == company_id, Customer.id.in_(all_ids))
            .all()
        ):
            names[cid] = cname
            kinds[cid] = "CLIENT"
        remaining = all_ids - names.keys()
        if remaining:
            for uid, uname, urole in (
                db.query(User.id, User.name, User.role).filter(User.id.in_(remaining)).all()
            ):
                names[uid] = uname
                kinds[uid] = getattr(urole, "value", urole)

    _extra = {"recipient_name", "recipient_kind"}
    return [
        CommunicationLogResponse(
            **{c: getattr(l, c) for c in CommunicationLogResponse.model_fields if c not in _extra},
            recipient_name=names.get(l.recipient_id),
            recipient_kind=kinds.get(l.recipient_id),
        )
        for l in logs
    ]


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_template_or_404(db: Session, company_id: UUID, template_id: UUID) -> CommunicationTemplate:
    tmpl = db.query(CommunicationTemplate).filter(
        CommunicationTemplate.template_id == template_id,
        CommunicationTemplate.company_id == company_id,
    ).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    return tmpl


def _get_permission_overrides(db: Session, company_id: UUID) -> dict:
    try:
        from app.infrastructure.db.models.tenant_config import TenantConfig
        config = db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
        return (config.permission_overrides or {}) if config else {}
    except Exception:
        return {}
