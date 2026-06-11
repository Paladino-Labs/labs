import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, Date, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class Payable(Base):
    """Conta a pagar — Sprint 17.

    Lifecycle: OPEN → PARTIALLY_PAID → PAID | CANCELLED
    closing_method: CASH_AT_CREATION | INSTALLMENTS
    source_type: STOCK_PURCHASE | MANUAL
    Financial-1: criar Payable NÃO cria Entry (receber ≠ reconhecer custo);
    pagar installment cria Movement OUTFLOW sem Entry.
    """
    __tablename__ = "payables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    description = Column(String(255), nullable=False)
    total_amount = Column(Numeric(15, 2), nullable=False)
    paid_amount = Column(Numeric(15, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="OPEN")
    due_date = Column(Date, nullable=True)
    closing_method = Column(String(20), nullable=False, default="CASH_AT_CREATION")
    source_type = Column(String(30), nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=True)
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


class PayableInstallment(Base):
    """Parcela de conta a pagar — Sprint 17. Status: OPEN | PAID."""
    __tablename__ = "payable_installments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payable_id = Column(UUID(as_uuid=True), ForeignKey("payables.id"), nullable=False)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    amount = Column(Numeric(15, 2), nullable=False)
    due_date = Column(Date, nullable=True)
    paid_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.payment_id"), nullable=True)
    installment_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
