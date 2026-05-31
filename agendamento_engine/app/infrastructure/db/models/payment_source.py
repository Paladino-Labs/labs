import uuid
import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class PaymentSource(Base):
    __tablename__ = "payment_sources"

    source_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    type = Column(String(20), nullable=False)      # CARD_CREDIT | CARD_DEBIT
    provider = Column(String(50), nullable=False)
    external_token = Column(Text, nullable=False)
    last4 = Column(String(4), nullable=True)
    brand = Column(String(50), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now())
