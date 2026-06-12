from datetime import datetime, timezone

from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


def _now_utc():
    return datetime.now(timezone.utc)


class PlatformSetting(Base):
    """Flags e configurações globais da plataforma (Sprint C).

    Tabela de PLATAFORMA — sem RLS por tenant; acesso exclusivamente via
    service layer (endpoints exigem PLATFORM_OWNER).
    """
    __tablename__ = "platform_settings"

    key = Column(String(100), primary_key=True)
    # JSON cross-dialect (JSONB no PostgreSQL) — mesmo padrão de audit_log.py
    value = Column(JSON, nullable=False)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    updated_at = Column(TIMESTAMP(timezone=True), nullable=False, default=_now_utc)
