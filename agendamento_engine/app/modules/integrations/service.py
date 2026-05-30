"""
Service de integrations/credentials — Sprint 5.

secret_encrypted nunca aparece em nenhuma resposta de API.
decrypt_secret() usado APENAS internamente em test_connection.
"""
import time
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.encryption import encrypt_secret, decrypt_secret, make_masked_preview
from app.core.audit.sensitive_context import SensitiveAuditContext, record_sensitive_action
from app.infrastructure.db.models.integration_credential import IntegrationCredential

logger = logging.getLogger(__name__)


def create_credential(
    db: Session,
    company_id: UUID,
    actor_id: UUID,
    actor_role: str,
    provider: str,
    label: str | None,
    secret: str,
    config: dict | None,
    ip_address: str | None = None,
) -> IntegrationCredential:
    cred = IntegrationCredential(
        company_id=company_id,
        provider=provider,
        label=label,
        secret_encrypted=encrypt_secret(secret),
        masked_preview=make_masked_preview(secret),
        config=config or {},
        status="ACTIVE",
        created_by=actor_id,
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def list_credentials(db: Session, company_id: UUID) -> list[IntegrationCredential]:
    return (
        db.query(IntegrationCredential)
        .filter(
            IntegrationCredential.company_id == company_id,
            IntegrationCredential.status == "ACTIVE",
        )
        .all()
    )


def rotate_credential(
    db: Session,
    company_id: UUID,
    credential_id: UUID,
    actor_id: UUID,
    actor_role: str,
    new_secret: str,
    ip_address: str | None = None,
) -> IntegrationCredential:
    from datetime import datetime, timezone

    old = _get_or_404(db, company_id, credential_id)

    # Revoga a antiga
    old.status = "REVOKED"
    old.revoked_at = datetime.now(timezone.utc)
    old.revoked_by = actor_id

    # Cria nova
    new_cred = IntegrationCredential(
        company_id=company_id,
        provider=old.provider,
        label=old.label,
        secret_encrypted=encrypt_secret(new_secret),
        masked_preview=make_masked_preview(new_secret),
        config=old.config,
        status="ACTIVE",
        created_by=actor_id,
    )
    db.add(new_cred)
    db.flush()

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role=actor_role,
            action="rotate_credential",
            resource_type="IntegrationCredential",
            resource_id=credential_id,
            company_id=company_id,
            ip_address=ip_address,
        ),
        db,
    )
    db.commit()
    db.refresh(new_cred)
    return new_cred


def revoke_credential(
    db: Session,
    company_id: UUID,
    credential_id: UUID,
    actor_id: UUID,
    actor_role: str,
    ip_address: str | None = None,
) -> None:
    from datetime import datetime, timezone

    cred = _get_or_404(db, company_id, credential_id)
    cred.status = "REVOKED"
    cred.revoked_at = datetime.now(timezone.utc)
    cred.revoked_by = actor_id

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role=actor_role,
            action="revoke_credential",
            resource_type="IntegrationCredential",
            resource_id=credential_id,
            company_id=company_id,
            ip_address=ip_address,
        ),
        db,
    )
    db.commit()


def test_credential(
    db: Session,
    company_id: UUID,
    credential_id: UUID,
    actor_id: UUID,
    actor_role: str,
    ip_address: str | None = None,
) -> dict:
    cred = _get_or_404(db, company_id, credential_id)

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role=actor_role,
            action="test_connection",
            resource_type="IntegrationCredential",
            resource_id=credential_id,
            company_id=company_id,
            reason="API connectivity test",
            ip_address=ip_address,
        ),
        db,
    )

    start = time.monotonic()
    try:
        plaintext = decrypt_secret(cred.secret_encrypted)
        success = bool(plaintext)
        latency_ms = (time.monotonic() - start) * 1000
        return {"success": success, "latency_ms": round(latency_ms, 2)}
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        return {"success": False, "latency_ms": round(latency_ms, 2), "error_message": str(exc)}


def _get_or_404(db: Session, company_id: UUID, credential_id: UUID) -> IntegrationCredential:
    cred = db.query(IntegrationCredential).filter(
        IntegrationCredential.credential_id == credential_id,
        IntegrationCredential.company_id == company_id,
    ).first()
    if not cred:
        raise HTTPException(status_code=404, detail="Credencial não encontrada")
    return cred
