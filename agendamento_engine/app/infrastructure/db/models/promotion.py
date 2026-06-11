"""Modelos do PromotionEngine — Sprint 16 (Decisão D1).

Promotion:
    discount_type: PERCENTAGE | FIXED_AMOUNT | OVERRIDE_PRICE | FREE_ITEM
    application_mode: AUTOMATIC | COUPON_REQUIRED
    status FSM: DRAFT → ACTIVE ⇄ PAUSED → EXPIRED | CANCELLED
    conditions JSONB: {min_order_value?, service_ids?, product_ids?,
        subscription_cycle_number_in?, subscription_cycle_min?,
        subscription_cycle_max?, customer_classification?}

Coupon:
    generation_type: BULK | SINGLE_USE | PER_CUSTOMER
    coupon_reopen_policy: NEVER_REOPEN (default) | REOPEN_ON_REFUND
    status: ACTIVE | EXHAUSTED | CANCELLED

CouponRedemption: rastro de uso; reverted_at preenchido no refund.

DiscountApplication: rastro D1 — uma linha por promoção aplicada, em
    sequência, com base_amount_at_application (residual antes do desconto).
    promotion_id NULL = desconto manual (manual-discount).
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    discount_type = Column(String(30), nullable=False)
    discount_value = Column(Numeric(15, 2), nullable=True)
    application_mode = Column(String(20), nullable=False, default="AUTOMATIC")
    cumulative = Column(Boolean, nullable=False, default=False)
    priority = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="DRAFT")
    valid_from = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    valid_until = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    max_uses = Column(Integer, nullable=True)
    max_uses_per_customer = Column(Integer, nullable=True)
    uses_count = Column(Integer, nullable=False, default=0)
    conditions = Column(JSONB, nullable=True)
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
    )


class Coupon(Base):
    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_coupons_company_code"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    promotion_id = Column(
        UUID(as_uuid=True), ForeignKey("promotions.id"), nullable=False, index=True
    )
    code = Column(String(50), nullable=False)
    generation_type = Column(String(20), nullable=False)
    max_uses = Column(Integer, nullable=True)
    uses_count = Column(Integer, nullable=False, default=0)
    coupon_reopen_policy = Column(String(20), nullable=False, default="NEVER_REOPEN")
    status = Column(String(20), nullable=False, default="ACTIVE")
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    expires_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class CouponRedemption(Base):
    __tablename__ = "coupon_redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    coupon_id = Column(UUID(as_uuid=True), ForeignKey("coupons.id"), nullable=False)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    payment_id = Column(
        UUID(as_uuid=True), ForeignKey("payments.payment_id"), nullable=False
    )
    redeemed_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    reverted_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    reverted_reason = Column(String(255), nullable=True)


class DiscountApplication(Base):
    __tablename__ = "discount_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True
    )
    payment_id = Column(
        UUID(as_uuid=True), ForeignKey("payments.payment_id"), nullable=False, index=True
    )
    # NULL = desconto manual (POST /payments/{id}/manual-discount)
    promotion_id = Column(UUID(as_uuid=True), ForeignKey("promotions.id"), nullable=True)
    sequence = Column(Integer, nullable=False)
    discount_type = Column(String(30), nullable=False)
    base_amount_at_application = Column(Numeric(15, 2), nullable=False)
    discount_amount = Column(Numeric(15, 2), nullable=False)
    reverted_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
