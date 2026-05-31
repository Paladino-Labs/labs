import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class Transfer(Base):
    """Transferência entre contas — movimentação interna, não fato econômico.

    Não gera Entry. Gera exatamente 2 Movements: TRANSFER_OUT + TRANSFER_IN.
    Status: REQUESTED | COMPLETED | FAILED
    """
    __tablename__ = "transfers"

    transfer_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    from_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    to_account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    amount = Column(Numeric(15, 2), nullable=False)
    status = Column(String, nullable=False, default="REQUESTED")  # REQUESTED | COMPLETED | FAILED
    requested_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    failed_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    failure_reason = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
