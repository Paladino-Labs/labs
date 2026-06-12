import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, Date, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ExternalStatementEntry(Base):
    """Linha importada de extrato externo (CSV) para conciliação.

    status: PENDING | MATCHED | DISMISSED
    direction: INFLOW | OUTFLOW
    matched_movement_id: vínculo UNIDIRECIONAL — Movement nunca é alterado.
    line_hash: SHA-256 da linha crua; UNIQUE (company_id, line_hash) garante
    idempotência de re-upload.
    """
    __tablename__ = "external_statement_entries"
    __table_args__ = (
        UniqueConstraint("company_id", "line_hash", name="uq_statement_company_line_hash"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    occurred_at = Column(Date, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    direction = Column(String(10), nullable=False)       # INFLOW | OUTFLOW
    description = Column(String(500), nullable=True)
    raw_line = Column(Text, nullable=True)               # linha original do CSV (auditoria)
    line_hash = Column(String(64), nullable=False)       # SHA-256 de raw_line
    status = Column(String(20), nullable=False, default="PENDING")
    matched_movement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("movements.movement_id"),
        nullable=True,
    )
    dismissed_reason = Column(String(255), nullable=True)
    dismissed_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    dismissed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    imported_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    import_batch_id = Column(UUID(as_uuid=True), nullable=False)
