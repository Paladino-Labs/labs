import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class CrmConfig(Base):
    """Thresholds de classificação CRM por tenant (1:1) — Sprint H."""
    __tablename__ = "crm_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, unique=True, index=True,
    )
    # NOVO: 1ª operação há <= X dias
    new_customer_days = Column(Integer, nullable=False, default=30)
    # FREQUENTE: >= N visitas em M meses
    frequent_min_visits = Column(Integer, nullable=False, default=3)
    frequent_period_months = Column(Integer, nullable=False, default=3)
    # EM_RISCO: sem operação > X × frequência média (mínimo risk_min_days)
    risk_multiplier = Column(Numeric(3, 1), nullable=False, default=2.0)
    risk_min_days = Column(Integer, nullable=False, default=45)
    # VIP: >= N visitas E >= R$ gasto total
    vip_min_visits = Column(Integer, nullable=False, default=10)
    vip_min_spend = Column(Numeric(15, 2), nullable=False, default=500.00)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=True,
        onupdate=lambda: datetime.now(timezone.utc),
    )


class CustomerClassification(Base):
    """Classificação computada — append por recomputação (Sprint H).

    Histórico preservado para auditoria; classificação atual = linha mais
    recente por (company_id, customer_id) via idx_customer_classifications_current.
    """
    __tablename__ = "customer_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    customer_id = Column(
        UUID(as_uuid=True), ForeignKey("customers.id"),
        nullable=False, index=True,
    )
    # NOVO | FREQUENTE | VIP | EM_RISCO | RECUPERADO | REGULAR
    classification = Column(String(20), nullable=False)
    computed_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    metrics_snapshot = Column(JSONB, nullable=False, default=dict)
