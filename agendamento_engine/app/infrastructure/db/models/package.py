import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class Package(Base):
    __tablename__ = "packages"

    package_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id    = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name          = Column(String, nullable=False)
    service_id    = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    total_cotas   = Column(Integer, nullable=False)
    price         = Column(Numeric(10, 2), nullable=False)
    validity_days = Column(Integer, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    service   = relationship("Service")
    purchases = relationship("PackagePurchase", back_populates="package")


class PackagePurchase(Base):
    __tablename__ = "package_purchases"

    purchase_id    = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id     = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id    = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    package_id     = Column(UUID(as_uuid=True), ForeignKey("packages.package_id"), nullable=False)
    seller_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    payment_id     = Column(UUID(as_uuid=True), ForeignKey("payments.payment_id"), nullable=True)
    total_price    = Column(Numeric(10, 2), nullable=False)
    # PENDING_PAYMENT | ACTIVE | REVOKED
    status         = Column(String, nullable=False, default="PENDING_PAYMENT")
    activated_at   = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at     = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    package  = relationship("Package", back_populates="purchases")
    customer = relationship("Customer")
    payment  = relationship("Payment")
