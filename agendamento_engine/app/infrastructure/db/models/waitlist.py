import uuid

import sqlalchemy as sa
from sqlalchemy import Boolean, CheckConstraint, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class WaitlistConfig(Base):
    """Configuração da fila de espera por tenant — Sprint G (1:1 com companies)."""
    __tablename__ = "waitlist_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, unique=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    priority_mode = Column(String(20), nullable=False, default="FIFO")
    # FIFO | PRIORITY_MANUAL
    notification_window_hours = Column(Integer, nullable=False, default=2)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
    )


class WaitlistEntry(Base):
    """Entrada na fila de espera — Sprint G.

    Escopo SERVICE | PROFESSIONAL | PRODUCT (apenas 1 dos 3 FKs preenchido).
    Lifecycle: WAITING → NOTIFIED → BOOKED | EXPIRED; CANCELLED a qualquer momento.
    Notificação NÃO reserva o slot — primeiro a agir leva.
    """
    __tablename__ = "waitlist_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    scope_type = Column(String(20), nullable=False)  # SERVICE | PROFESSIONAL | PRODUCT
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=True)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    status = Column(String(20), nullable=False, default="WAITING")
    # WAITING | NOTIFIED | BOOKED | EXPIRED | CANCELLED
    priority = Column(Integer, nullable=False, default=0)
    source_channel = Column(String(20), nullable=False, default="PAINEL")  # PAINEL | BOT
    notified_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    expires_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'SERVICE' AND service_id IS NOT NULL"
            " AND professional_id IS NULL AND product_id IS NULL)"
            " OR (scope_type = 'PROFESSIONAL' AND professional_id IS NOT NULL"
            " AND service_id IS NULL AND product_id IS NULL)"
            " OR (scope_type = 'PRODUCT' AND product_id IS NOT NULL"
            " AND service_id IS NULL AND professional_id IS NULL)",
            name="check_waitlist_scope",
        ),
    )
