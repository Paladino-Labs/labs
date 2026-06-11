import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, Date, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class Expense(Base):
    """Despesa operacional — Sprint 18.

    Lifecycle: PENDENTE → PAGA | CANCELLED
    recurrence_rule: {"frequency": "MONTHLY", "day_of_month": int, "end_date"?: "YYYY-MM-DD"}
    parent_expense_id encadeia instâncias geradas pela recorrência.
    supplier_id sem FK — suppliers não existe ainda (FK adicionada no Sprint 17).
    """
    __tablename__ = "expenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    description = Column(String(255), nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    category = Column(String(50), nullable=False)        # EntryCategory DESPESA (validado no service)
    supplier_id = Column(UUID(as_uuid=True), nullable=True)
    due_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="PENDENTE")  # PENDENTE | PAGA | CANCELLED
    paid_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    paid_amount = Column(Numeric(15, 2), nullable=True)
    recurrence_rule = Column(JSONB, nullable=True)
    parent_expense_id = Column(UUID(as_uuid=True), ForeignKey("expenses.id"), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
