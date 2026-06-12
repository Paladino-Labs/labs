import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


def _now_utc():
    return datetime.now(timezone.utc)


class ImpersonationGrant(Base):
    """Grant time-boxed de impersonation cross-tenant (Sprint C, PlatformSecurity-1).

    Tabela de PLATAFORMA — sem RLS por tenant; acesso só via service layer.
    Quase-append-only: trigger no banco bloqueia DELETE e qualquer UPDATE
    que não seja a revogação (revoked_at NULL → valor, demais campos intactos).
    """
    __tablename__ = "impersonation_grants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    # READ_ONLY | ELEVATED
    mode = Column(String(20), nullable=False, default="READ_ONLY")
    reason = Column(Text, nullable=False)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    # NULL = ativo (se não expirado). Revogação é única e irreversível.
    revoked_at = Column(TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_now_utc)

    @property
    def is_active(self) -> bool:
        if self.revoked_at is not None:
            return False
        expires = self.expires_at
        if expires is not None and expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return expires is not None and expires > datetime.now(timezone.utc)
