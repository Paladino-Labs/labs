import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class DepositPolicy(Base):
    """Política de sinal/depósito para agendamentos.

    service_id NULL = política global do tenant.
    service_id preenchido = política específica para o serviço.
    deposit_type: FIXED_AMOUNT | PERCENTAGE
    """
    __tablename__ = "deposit_policies"

    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)

    deposit_type = Column(String(20), nullable=False)   # FIXED_AMOUNT | PERCENTAGE
    deposit_value = Column(Numeric(10, 2), nullable=False)

    refundable_until_hours_before = Column(Integer, nullable=False, default=24)
    refund_on_tenant_fault = Column(Boolean, nullable=False, default=True)
    retain_on_no_show = Column(Boolean, nullable=False, default=True)
    commission_on_retained_deposit = Column(Boolean, nullable=False, default=False)

    created_at = Column(sa.TIMESTAMP(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
