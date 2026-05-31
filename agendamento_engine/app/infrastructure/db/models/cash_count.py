import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class CashCount(Base):
    """Conferência de caixa.

    discrepancy = counted_amount - expected_amount (computado na service layer).
    resolution: ADJUSTED | NO_ADJUSTMENT
    entry_id: aponta para Entry AJUSTE criada se resolution=ADJUSTED e discrepancy != 0.
    notes: obrigatório quando resolution=ADJUSTED e discrepancy != 0 (422 na service layer).
    """
    __tablename__ = "cash_counts"

    cash_count_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    expected_amount = Column(Numeric(15, 2), nullable=False)
    counted_amount = Column(Numeric(15, 2), nullable=False)
    discrepancy = Column(Numeric(15, 2), nullable=False)   # counted - expected
    resolution = Column(String, nullable=False)            # ADJUSTED | NO_ADJUSTMENT
    notes = Column(Text, nullable=True)
    entry_id = Column(
        UUID(as_uuid=True),
        ForeignKey("entries.entry_id"),
        nullable=True,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
