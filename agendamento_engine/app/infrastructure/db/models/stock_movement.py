import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class StockMovement(Base):
    """Movimento de estoque — Sprint 17.

    movement_type: ENTRADA | VENDA | USO_INTERNO | PERDA | AJUSTE
    unit_cost: preenchido em ENTRADA (custo de compra); nas saídas a
    valoração usa o avg_cost do produto no momento do movimento.
    source_type: SUPPLIER_ORDER | MANUAL | OPERATION | ADJUSTMENT
    """
    __tablename__ = "stock_movements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    movement_type = Column(String(30), nullable=False)
    quantity = Column(Numeric(15, 3), nullable=False)
    unit_cost = Column(Numeric(15, 2), nullable=True)
    source_type = Column(String(30), nullable=True)
    source_id = Column(UUID(as_uuid=True), nullable=True)
    notes = Column(Text, nullable=True)
    occurred_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
