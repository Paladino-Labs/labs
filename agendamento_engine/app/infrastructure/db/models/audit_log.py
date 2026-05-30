import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Numeric, TIMESTAMP, JSON
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


def _now_utc():
    return datetime.now(timezone.utc)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # Append-only enforced via triggers no banco (prevent_audit_modification).
    # Nunca emitir UPDATE nem DELETE nesta tabela via ORM.

    audit_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=True, index=True)
    actor_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    actor_role = Column(String(50), nullable=False)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    amount = Column(Numeric(15, 2), nullable=True)
    account_id = Column(UUID(as_uuid=True), nullable=True)
    reason = Column(Text, nullable=True)
    correlation_id = Column(UUID(as_uuid=True), nullable=True)
    # JSON cross-dialect (maps to JSONB on PostgreSQL, TEXT/JSON on SQLite)
    before_snapshot = Column(JSON, nullable=True)
    after_snapshot = Column(JSON, nullable=True)
    occurred_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_now_utc,
        index=True,
    )
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
