"""
PlatformService — Sprint C (Painel Owner Paladino).

Gestão de tenants, impersonation grants, feature flags (por tenant e globais)
e redispatch mínimo de comunicação (Decisão D7). Todas as operações são
chamadas exclusivamente por endpoints que exigem PLATFORM_OWNER.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.infrastructure.db.models import (
    Appointment,
    Company,
    CommunicationLog,
    Customer,
    ImpersonationGrant,
    PlatformSetting,
    TenantConfig,
    User,
    WhatsAppConnection,
)

logger = logging.getLogger(__name__)

TENANT_STATUSES = {"TRIAL", "ACTIVE", "SUSPENDED", "CHURNED"}

# ELEVATED dá escrita cross-tenant — exige justificativa substantiva.
ELEVATED_REASON_MIN_CHARS = 20

DEFAULT_GRANT_DURATION_MINUTES = 30


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_company_or_404(db: Session, company_id: UUID) -> Company:
    company = db.query(Company).filter(Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Tenant não encontrado")
    return company


# ── Gestão de tenants ────────────────────────────────────────────────────────

def list_tenants(
    db: Session,
    status: Optional[str] = None,
    created_after: Optional[datetime] = None,
    search_name: Optional[str] = None,
) -> list[Company]:
    q = db.query(Company)
    if status:
        q = q.filter(Company.status == status)
    if created_after:
        q = q.filter(Company.created_at >= created_after)
    companies = q.all()
    if search_name:
        needle = search_name.lower()
        companies = [c for c in companies if needle in (c.name or "").lower()]
    return companies


def get_tenant_health(db: Session, company_id: UUID) -> dict:
    """Métricas mínimas de saúde do tenant (DoD Sprint C).

    Agregações em Python sobre queries filtradas — volumes por tenant são
    baixos no Estágio 0 e o padrão mantém compatibilidade com o FakeDB.
    """
    company = _get_company_or_404(db, company_id)
    now = _now()
    cutoff_30d = now - timedelta(days=30)
    cutoff_7d = now - timedelta(days=7)

    total_users = db.query(User).filter(User.company_id == company_id).count()
    total_customers = (
        db.query(Customer).filter(Customer.company_id == company_id).count()
    )

    appointments = (
        db.query(Appointment).filter(Appointment.company_id == company_id).all()
    )
    appointments_30d = sum(
        1
        for a in appointments
        if a.status in ("COMPLETED", "CONFIRMED")
        and a.start_at is not None
        and a.start_at >= cutoff_30d
    )
    updated_ats = [a.updated_at for a in appointments if a.updated_at is not None]
    last_activity_at = max(updated_ats) if updated_ats else None

    communication_failures_7d = (
        db.query(CommunicationLog)
        .filter(
            CommunicationLog.company_id == company_id,
            CommunicationLog.status == "FAILED",
            CommunicationLog.created_at >= cutoff_7d,
        )
        .count()
    )

    whatsapp_conn = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.company_id == company_id,
            WhatsAppConnection.status == "CONNECTED",
        )
        .first()
    )

    return {
        "company_id": str(company_id),
        "status": company.status,
        "total_users": total_users,
        "total_customers": total_customers,
        "appointments_30d": appointments_30d,
        "last_activity_at": last_activity_at.isoformat() if last_activity_at else None,
        "communication_failures_7d": communication_failures_7d,
        "asaas_connected": company.external_account_id is not None,
        "whatsapp_connected": whatsapp_conn is not None,
    }


def set_tenant_status(
    db: Session,
    company_id: UUID,
    status: str,
    reason: Optional[str],
    platform_user_id: UUID,
) -> Company:
    """Transição de status do tenant (SUSPENDED/ACTIVE/CHURNED/TRIAL) com audit."""
    if status not in TENANT_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Status inválido. Use um de: {sorted(TENANT_STATUSES)}",
        )
    if status == "SUSPENDED" and not (reason and reason.strip()):
        raise HTTPException(
            status_code=422, detail="reason obrigatório para suspensão"
        )

    company = _get_company_or_404(db, company_id)
    before_status = company.status
    company.status = status

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="tenant_status_changed",
            resource_type="Company",
            resource_id=company_id,
            company_id=company_id,
            reason=reason,
            before_snapshot={"status": before_status},
            after_snapshot={"status": status},
        ),
        db,
    )
    db.commit()

    if status == "SUSPENDED":
        _notify_tenant_owner_suspension(db, company, reason)

    return company


def suspend_tenant(
    db: Session, company_id: UUID, reason: str, platform_user_id: UUID
) -> Company:
    return set_tenant_status(db, company_id, "SUSPENDED", reason, platform_user_id)


def reactivate_tenant(db: Session, company_id: UUID, platform_user_id: UUID) -> Company:
    return set_tenant_status(db, company_id, "ACTIVE", None, platform_user_id)


def _notify_tenant_owner_suspension(
    db: Session, company: Company, reason: Optional[str]
) -> None:
    """Notifica o OWNER do tenant por email (best-effort — nunca bloqueia)."""
    try:
        owner = (
            db.query(User)
            .filter(
                User.company_id == company.id,
                User.role == "OWNER",
                User.active == True,  # noqa: E712
            )
            .first()
        )
        if not owner or not owner.email:
            return
        # Email direto (padrão _send_reset_email_direct): suspensão é evento de
        # plataforma — CommunicationService.dispatch do próprio tenant não é
        # apropriado para avisar que o tenant foi suspenso.
        from app.modules.platform.emails import send_suspension_email

        send_suspension_email(owner.email, owner.name or "", company.name, reason)
    except Exception:
        logger.exception(
            "Falha ao notificar OWNER do tenant %s sobre suspensão", company.id
        )


# ── Impersonation ────────────────────────────────────────────────────────────

def create_impersonation_grant(
    db: Session,
    platform_user_id: UUID,
    company_id: UUID,
    mode: str,
    reason: str,
    duration_minutes: int = DEFAULT_GRANT_DURATION_MINUTES,
) -> tuple[ImpersonationGrant, str]:
    """Cria grant. Retorna (grant, grant_id para o header X-Impersonate-Grant)."""
    if mode not in ("READ_ONLY", "ELEVATED"):
        raise HTTPException(status_code=422, detail="mode deve ser READ_ONLY ou ELEVATED")
    if not (reason and reason.strip()):
        raise HTTPException(status_code=422, detail="reason obrigatório")
    if mode == "ELEVATED" and len(reason.strip()) < ELEVATED_REASON_MIN_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"ELEVATED exige reason detalhado (mínimo {ELEVATED_REASON_MIN_CHARS} caracteres)",
        )
    if duration_minutes < 1 or duration_minutes > 480:
        raise HTTPException(
            status_code=422, detail="duration_minutes deve estar entre 1 e 480"
        )

    _get_company_or_404(db, company_id)

    grant = ImpersonationGrant(
        platform_user_id=platform_user_id,
        company_id=company_id,
        mode=mode,
        reason=reason.strip(),
        expires_at=_now() + timedelta(minutes=duration_minutes),
    )
    db.add(grant)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="impersonation_grant_created",
            resource_type="ImpersonationGrant",
            resource_id=grant.id,
            company_id=company_id,
            reason=reason,
            after_snapshot={"mode": mode, "expires_at": grant.expires_at.isoformat()},
        ),
        db,
    )
    db.commit()
    return grant, str(grant.id)


def revoke_impersonation_grant(
    db: Session, grant_id: UUID, platform_user_id: UUID
) -> ImpersonationGrant:
    """Seta revoked_at. Não deleta (trigger no banco bloqueia DELETE)."""
    grant = (
        db.query(ImpersonationGrant)
        .filter(ImpersonationGrant.id == grant_id)
        .first()
    )
    if not grant:
        raise HTTPException(status_code=404, detail="Grant não encontrado")
    if grant.platform_user_id != platform_user_id:
        raise HTTPException(status_code=403, detail="Grant pertence a outro usuário")
    if grant.revoked_at is not None:
        raise HTTPException(status_code=422, detail="Grant já revogado")

    grant.revoked_at = _now()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="impersonation_grant_revoked",
            resource_type="ImpersonationGrant",
            resource_id=grant.id,
            company_id=grant.company_id,
        ),
        db,
    )
    db.commit()
    return grant


def list_active_grants(db: Session, platform_user_id: UUID) -> list[ImpersonationGrant]:
    grants = (
        db.query(ImpersonationGrant)
        .filter(ImpersonationGrant.platform_user_id == platform_user_id)
        .all()
    )
    return [g for g in grants if g.is_active]


# ── Feature flags por tenant (TenantConfig.permission_overrides) ─────────────

def get_tenant_flags(db: Session, company_id: UUID) -> dict:
    config = (
        db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="TenantConfig não encontrado")
    return config.permission_overrides or {}


def set_tenant_flag(
    db: Session, company_id: UUID, key: str, value, platform_user_id: UUID
) -> dict:
    config = (
        db.query(TenantConfig).filter(TenantConfig.company_id == company_id).first()
    )
    if not config:
        raise HTTPException(status_code=404, detail="TenantConfig não encontrado")

    overrides = dict(config.permission_overrides or {})
    before_value = overrides.get(key)
    overrides[key] = value
    # Reatribuição (não mutação in-place) — JSONB só detecta mudança de referência.
    config.permission_overrides = overrides

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="tenant_flag_changed",
            resource_type="TenantConfig",
            resource_id=config.tenant_config_id,
            company_id=company_id,
            before_snapshot={key: before_value},
            after_snapshot={key: value},
        ),
        db,
    )
    db.commit()
    return overrides


# ── Platform settings (globais) ──────────────────────────────────────────────

def get_platform_settings(db: Session) -> dict:
    rows = db.query(PlatformSetting).all()
    return {row.key: row.value for row in rows}


def set_platform_setting(db: Session, key: str, value, platform_user_id: UUID) -> dict:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == key).first()
    before_value = row.value if row else None
    if row:
        row.value = value
        row.updated_by = platform_user_id
        row.updated_at = _now()
    else:
        row = PlatformSetting(key=key, value=value, updated_by=platform_user_id)
        db.add(row)

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="platform_setting_changed",
            resource_type="PlatformSetting",
            before_snapshot={key: before_value},
            after_snapshot={key: value},
        ),
        db,
    )
    db.commit()
    return {"key": key, "value": value}


# ── Redispatch de comunicação (Decisão D7 — mínimo) ──────────────────────────

def redispatch_communication(
    db: Session, log_id: UUID, reason: str, platform_user_id: UUID
) -> CommunicationLog:
    """Re-envia uma mensagem FALHA. Cria NOVO CommunicationLog (não reutiliza).

    O context original de renderização não é persistido em CommunicationLog,
    então re-renderizar via dispatch() é impossível — re-enviamos o
    rendered_body original pelo mesmo canal (padrão drain_scheduled).
    """
    if not (reason and reason.strip()):
        raise HTTPException(status_code=422, detail="reason obrigatório")

    log = (
        db.query(CommunicationLog).filter(CommunicationLog.log_id == log_id).first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="CommunicationLog não encontrado")
    if log.status != "FAILED":
        raise HTTPException(
            status_code=422, detail="Apenas logs com status FAILED são elegíveis"
        )
    if not log.rendered_body:
        raise HTTPException(
            status_code=422,
            detail="Log sem rendered_body — reenvio impossível (context não persistido)",
        )

    new_log = CommunicationLog(
        company_id=log.company_id,
        template_id=log.template_id,
        event_type=log.event_type,
        channel=log.channel,
        recipient_id=log.recipient_id,
        recipient_type=log.recipient_type,
        rendered_body=log.rendered_body,
        status="FAILED",  # pessimista; vira SENT após envio bem-sucedido
    )

    try:
        _resend_rendered(db, log)
        new_log.status = "SENT"
        new_log.sent_at = _now()
    except Exception as exc:
        logger.exception("redispatch: reenvio falhou para log %s", log_id)
        new_log.error_message = str(exc)

    db.add(new_log)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=platform_user_id,
            actor_role="PLATFORM_OWNER",
            action="communication_redispatched",
            resource_type="CommunicationLog",
            resource_id=log_id,
            company_id=log.company_id,
            reason=reason,
            after_snapshot={"new_log_id": str(new_log.log_id), "status": new_log.status},
        ),
        db,
    )
    db.commit()
    return new_log


def _resend_rendered(db: Session, log: CommunicationLog) -> None:
    """Reenvia o rendered_body do log original pelo canal de origem."""
    if log.channel == "EMAIL":
        customer = (
            db.query(Customer).filter(Customer.id == log.recipient_id).first()
        )
        recipient_email = getattr(customer, "email", None)
        if not recipient_email:
            user = db.query(User).filter(User.id == log.recipient_id).first()
            recipient_email = getattr(user, "email", None)
        if not recipient_email:
            raise RuntimeError("Destinatário sem email — reenvio EMAIL impossível")

        from app.modules.communication.service import communication_service
        from app.infrastructure.db.models import CommunicationSetting

        comm_settings = (
            db.query(CommunicationSetting)
            .filter(CommunicationSetting.company_id == log.company_id)
            .first()
        )
        communication_service._send_email(
            comm_settings,
            {"recipient_email": recipient_email},
            log.rendered_body,
            db,
        )
        return

    # WHATSAPP (e fallback): mesmo caminho do drain_scheduled
    customer = db.query(Customer).filter(Customer.id == log.recipient_id).first()
    phone = getattr(customer, "phone", None)
    if not phone:
        raise RuntimeError("Destinatário sem telefone — reenvio WHATSAPP impossível")

    conn = (
        db.query(WhatsAppConnection)
        .filter(
            WhatsAppConnection.company_id == log.company_id,
            WhatsAppConnection.status == "CONNECTED",
        )
        .first()
    )
    if not conn:
        raise RuntimeError(f"Empresa {log.company_id} sem WhatsApp conectado")

    from app.modules.whatsapp import evolution_client

    evolution_client.send_text(conn.instance_name, phone, log.rendered_body)
