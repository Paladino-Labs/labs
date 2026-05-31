import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ReconciliationRecord(Base):
    """Registro de reconciliação de conta.

    Status: OPEN | CLOSED
    Movements são vinculados via movement_reconciliations (tabela separada).
    """
    __tablename__ = "reconciliation_records"

    reconciliation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    status = Column(String, nullable=False, default="OPEN")  # OPEN | CLOSED
    opened_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    closed_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    opened_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    closed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text, nullable=True)
