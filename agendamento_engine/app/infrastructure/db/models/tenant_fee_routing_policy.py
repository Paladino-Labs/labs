import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class TenantFeeRoutingPolicy(Base):
    """Política de rateio de taxas por fonte de receita.

    Chave natural: (company_id, fee_source).
    Sem FK em tenant_configs — lookup direto.

    fee_source válidos:
        ASAAS_PIX | ASAAS_CARD | MAQUININHA_DEBIT | MAQUININHA_CREDIT
        | ANTECIPACAO | ESTORNO | RECORRENTE_FEE
    """
    __tablename__ = "tenant_fee_routing_policies"

    policy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    fee_source = Column(String, nullable=False)

    # Rateio em percentual — soma deve ser 100 (constraint no banco)
    client_share = Column(Numeric(5, 2), nullable=False, default=0)
    tenant_share = Column(Numeric(5, 2), nullable=False, default=100)
    professional_share = Column(Numeric(5, 2), nullable=False, default=0)

    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
