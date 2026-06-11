import uuid
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, Integer, Numeric, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.infrastructure.db.base import Base


class TenantConfig(Base):
    __tablename__ = "tenant_configs"

    tenant_config_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Operacional
    timezone = Column(String(50), nullable=False, default="America/Sao_Paulo")
    soft_reservation_ttl_min = Column(Integer, nullable=False, default=15)
    draft_expiration_min = Column(Integer, nullable=False, default=60)
    requested_expiration_h = Column(Integer, nullable=False, default=24)
    no_show_threshold_min = Column(Integer, nullable=False, default=30)
    no_penalty_cancel_h = Column(Integer, nullable=False, default=12)
    require_payment_upfront = Column(Boolean, nullable=False, default=False)
    allow_negative_stock = Column(Boolean, nullable=False, default=False)
    default_commission_pct = Column(Numeric(5, 2), nullable=False, default=Decimal("40.00"))

    # fee_routing_policy_id removido na migration l1m2n3o4p5q6 (Sprint 6)
    # Lookup agora via (company_id, fee_source) em tenant_fee_routing_policies

    # Contábil — ACCRUAL bloqueado por trigger no banco no Estágio 0
    accounting_mode = Column(
        SAEnum("CASH", "ACCRUAL", name="accountingmode", create_type=False),
        nullable=False,
        default="CASH",
    )

    # RBAC opt-ins granulares: { "OPERATOR": { "create_manual_adjustment": true } }
    permission_overrides = Column(JSONB, nullable=False, default=dict)

    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
