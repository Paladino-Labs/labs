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
    # total_cotas mantido como coluna derivada = sum(item.quantity), sincronizado na criação
    total_cotas   = Column(Integer, nullable=False)
    price         = Column(Numeric(10, 2), nullable=False)
    validity_days = Column(Integer, nullable=True)
    is_active     = Column(Boolean, nullable=False, default=True)
    created_at    = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at    = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    items     = relationship(
        "PackageItem",
        back_populates="package",
        order_by="PackageItem.display_order",
        cascade="all, delete-orphan",
    )
    purchases = relationship("PackagePurchase", back_populates="package")


class PackageItem(Base):
    __tablename__ = "package_items"

    item_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    package_id    = Column(UUID(as_uuid=True), ForeignKey("packages.package_id", ondelete="CASCADE"), nullable=False)
    company_id    = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    item_type     = Column(String(10), nullable=False)   # 'SERVICE' | 'PRODUCT'
    service_id    = Column(UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    product_id    = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    quantity      = Column(Integer, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)

    service = relationship("Service")
    product = relationship("Product")
    package = relationship("Package", back_populates="items")


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
