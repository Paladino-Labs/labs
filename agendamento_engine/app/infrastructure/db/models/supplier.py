import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, ForeignKey, Text

from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base, TimestampMixin


class Supplier(Base, TimestampMixin):
    """Fornecedor — Sprint 17.

    Desativável, nunca deletado (Princípio 10): DELETE na API → active=False.
    """
    __tablename__ = "suppliers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    contact = Column(String(255), nullable=True)
    document = Column(String(20), nullable=True)
    active = Column(Boolean, nullable=False, default=True)


class SupplierOrder(Base):
    """Pedido de fornecedor — Sprint 17.

    Status: PENDING | RECEIVED | CANCELLED
    receive_order cria direto em RECEIVED (entrada de estoque efetivada).
    """
    __tablename__ = "supplier_orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    supplier_id = Column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    ordered_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    received_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
