import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class TenantFeeRoutingPolicy(Base):
    """Política de rateio e cálculo de taxas por fonte de receita.

    Chave natural: (company_id, fee_source).
    Sem FK em tenant_configs — lookup direto.

    fee_source válidos:
        ASAAS_PIX | ASAAS_CARD | MAQUININHA_DEBIT | MAQUININHA_CREDIT
        | ANTECIPACAO | ESTORNO | RECORRENTE_FEE

    fee_percentage: taxa MDR aplicada ao valor bruto (ex: 3.99 = 3,99%).
    fee_flat: taxa fixa adicional por transação (ex: 0.30 = R$0,30).
    is_active: políticas inativas não geram cobrança de taxa.
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

    # Cálculo de taxa (MDR) para pagamentos manuais (maquininha)
    fee_percentage = Column(Numeric(7, 4), nullable=False, default=0)
    fee_flat = Column(Numeric(10, 2), nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
