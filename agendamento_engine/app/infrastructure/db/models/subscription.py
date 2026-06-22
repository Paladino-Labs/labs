import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    plan_id          = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id       = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name             = Column(String, nullable=False)
    # cotas_per_cycle mantido como coluna derivada = sum(item.quantity), sincronizado na criação
    cotas_per_cycle  = Column(Integer, nullable=False)
    price            = Column(Numeric(10, 2), nullable=False)
    cycle_days       = Column(Integer, nullable=False, default=30)
    rollover_enabled = Column(Boolean, nullable=False, default=False)
    is_active        = Column(Boolean, nullable=False, default=True)
    created_at       = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at       = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    items         = relationship(
        "PlanItem",
        back_populates="plan",
        order_by="PlanItem.display_order",
        cascade="all, delete-orphan",
    )
    subscriptions = relationship("CustomerSubscription", back_populates="plan")


class PlanItem(Base):
    __tablename__ = "plan_items"

    item_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id       = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.plan_id", ondelete="CASCADE"), nullable=False)
    company_id    = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    item_type     = Column(String(10), nullable=False)   # 'SERVICE' | 'PRODUCT'
    service_id    = Column(UUID(as_uuid=True), ForeignKey("services.id", ondelete="SET NULL"), nullable=True)
    product_id    = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    quantity      = Column(Integer, nullable=False)
    display_order = Column(Integer, nullable=False, default=0)

    service = relationship("Service")
    product = relationship("Product")
    plan    = relationship("SubscriptionPlan", back_populates="items")


class CustomerSubscription(Base):
    __tablename__ = "customer_subscriptions"

    subscription_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id      = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id     = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    plan_id         = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.plan_id"), nullable=False)
    # ACTIVE | PAUSED | OVERDUE | SUSPENDED | CANCELLED
    status          = Column(String, nullable=False, default="ACTIVE")
    next_billing_at = Column(sa.TIMESTAMP(timezone=True), nullable=False)
    overdue_since   = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    paused_at       = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    cancelled_at    = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at      = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    plan     = relationship("SubscriptionPlan", back_populates="subscriptions")
    customer = relationship("Customer")
