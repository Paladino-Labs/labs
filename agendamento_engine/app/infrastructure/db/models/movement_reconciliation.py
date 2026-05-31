import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class MovementReconciliation(Base):
    """Vínculo entre Movement e ReconciliationRecord.

    Movement permanece 100% append-only — nenhum campo de Movement é alterado.
    company_id desnormalizado para RLS sem JOIN.
    """
    __tablename__ = "movement_reconciliations"

    __table_args__ = (
        UniqueConstraint("movement_id", "reconciliation_id", name="uq_movement_reconciliation"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    movement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("movements.movement_id"),
        nullable=False,
    )
    reconciliation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("reconciliation_records.reconciliation_id"),
        nullable=False,
    )
    reconciled_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    reconciled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
