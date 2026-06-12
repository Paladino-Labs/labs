import uuid
import sqlalchemy as sa
from sqlalchemy import Column, String, ForeignKey, Boolean, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    """
    Cliente da barbearia (quem agenda).
    Tabela renomeada de 'clients' para 'customers' na migration f3a9e1d72b04.

    Constraint de unicidade: (company_id, phone) — o mesmo telefone pode existir
    em empresas diferentes, mas não pode se repetir dentro da mesma empresa.
    Migration: f1e2d3c4b5a6 removeu a constraint legada UNIQUE(phone) e criou
    a correta UNIQUE(company_id, phone).
    """
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)        # observações internas (visível apenas no painel)
    # Campos custom por tenant (Sprint H — CRM); nunca vazam para outra empresa
    custom_fields = Column(JSONB, nullable=False, default=dict,
                           server_default=sa.text("'{}'::jsonb"))
    active = Column(Boolean, default=True, nullable=False)
    # ID do customer no Asaas (cus_...). Preenchido na primeira cobrança via Asaas.
    asaas_customer_id = Column(String(50), nullable=True)
    # Vínculo com a identidade global Paladino (Sprint A). Nullable: clientes
    # pré-Sprint A ficam NULL até o backfill (scripts/backfill_identity.py).
    identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paladino_identities.id", ondelete="SET NULL"),
        nullable=True,
    )

    company = relationship("Company", back_populates="customers")
    appointments = relationship("Appointment", back_populates="customer", lazy="dynamic")

    __table_args__ = (
        UniqueConstraint("company_id", "phone", name="uq_customers_company_phone"),
    )
