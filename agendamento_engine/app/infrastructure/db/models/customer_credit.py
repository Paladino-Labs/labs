import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class CustomerCredit(Base):
    __tablename__ = "customer_credits"

    credit_id        = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id       = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id      = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    # PACKAGE | SUBSCRIPTION | GRANT_COTA
    entitlement_type = Column(String, nullable=False)
    source_id        = Column(UUID(as_uuid=True), nullable=True)
    total_cotas      = Column(Integer, nullable=False)
    remaining_cotas  = Column(Integer, nullable=False)
    # ACTIVE | EXHAUSTED | EXPIRED | REVOKED
    status           = Column(String, nullable=False, default="ACTIVE")
    granted_at       = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at       = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    customer      = relationship("Customer")
    consumptions  = relationship("CustomerCreditConsumption", back_populates="credit")


class CustomerCreditConsumption(Base):
    __tablename__ = "customer_credit_consumptions"

    consumption_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    credit_id      = Column(UUID(as_uuid=True), ForeignKey("customer_credits.credit_id"), nullable=False, index=True)
    company_id     = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id    = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    consumed_at    = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    credit = relationship("CustomerCredit", back_populates="consumptions")
