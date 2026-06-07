import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, ForeignKey, Numeric, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class CommissionPolicy(Base):
    __tablename__ = "commission_policies"

    policy_id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id            = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id       = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=True)
    service_id            = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    # GROSS_SERVICE | NET_SERVICE | GROSS_OPERATION | CUSTOM_AMOUNT
    commission_base       = Column(String, nullable=False)
    # BEFORE_FEES | AFTER_FEES
    commission_fee_policy = Column(String, nullable=False)
    rate                  = Column(Numeric(5, 2), nullable=True)
    fixed_amount          = Column(Numeric(10, 2), nullable=True)
    is_active             = Column(Boolean, nullable=False, default=True)
    created_at            = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at            = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    commissions   = relationship("Commission", back_populates="policy")
    professional  = relationship("Professional")
    service       = relationship("Service")


class CommissionPayout(Base):
    __tablename__ = "commission_payouts"

    payout_id       = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id      = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    total_amount    = Column(Numeric(10, 2), nullable=False)
    account_id      = Column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    # PENDING | PAID | CANCELLED
    status          = Column(String, nullable=False, default="PENDING")
    paid_at         = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    created_by      = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at      = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    commissions  = relationship("Commission", back_populates="payout")
    professional = relationship("Professional")


class Commission(Base):
    __tablename__ = "commissions"

    commission_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id        = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id   = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    policy_id         = Column(UUID(as_uuid=True), ForeignKey("commission_policies.policy_id"), nullable=True)
    appointment_id    = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    # SERVICE_RENDERED | PACKAGE_SOLD | SUBSCRIPTION_SOLD
    operation_type    = Column(String, nullable=False)
    gross_amount      = Column(Numeric(10, 2), nullable=False)
    commission_amount = Column(Numeric(10, 2), nullable=False)
    # CALCULATED | DUE | PAID | REVERSED
    status            = Column(String, nullable=False, default="CALCULATED")
    due_date          = Column(Date, nullable=True)
    paid_at           = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    payout_id         = Column(UUID(as_uuid=True), ForeignKey("commission_payouts.payout_id"), nullable=True)
    created_at        = Column(sa.TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    policy       = relationship("CommissionPolicy", back_populates="commissions")
    payout       = relationship("CommissionPayout", back_populates="commissions")
    professional = relationship("Professional")
