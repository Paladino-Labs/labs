import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Boolean, Column, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates

from app.infrastructure.db.base import Base


class Payment(Base):
    """Pagamento — lifecycle FSM: PENDING → CONFIRMED → REFUNDED | FAILED | CANCELLED.

    provider é imutável após criação:
      1. Trigger de banco (payment_provider_immutable) — UPDATE OF provider rejeitado.
      2. @validates ORM — defesa em profundidade.
    """
    __tablename__ = "payments"

    payment_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    currency = Column(String(3), nullable=False, default="BRL")

    gross_catalog_amount = Column(Numeric(15, 2), nullable=False)
    discount_amount = Column(Numeric(15, 2), nullable=False, default=0)
    net_charged_amount = Column(Numeric(15, 2), nullable=False)
    provider_fee = Column(Numeric(15, 2), nullable=False, default=0)

    # Método de pagamento (separado de payment_source)
    # CASH | PIX | BOLETO | CARD_CREDIT | CARD_DEBIT | MAQUININHA
    payment_method = Column(String(50), nullable=False)
    # Nulo para CASH/PIX/BOLETO; preenchido para cartão salvo
    payment_source_id = Column(UUID(as_uuid=True), ForeignKey("payment_sources.source_id"), nullable=True)

    # Provider — imutável após criação
    provider = Column(String(50), nullable=False)
    target_account_id = Column(UUID(as_uuid=True), ForeignKey("accounts.account_id"), nullable=False)
    external_charge_id = Column(String, nullable=True)

    status = Column(String(20), nullable=False, default="PENDING")
    manual_override_count = Column(Integer, nullable=False, default=0)

    created_at = Column(sa.TIMESTAMP(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
    paid_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    refunded_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    @validates("provider")
    def validate_provider_immutable(self, key: str, value):
        if self._sa_instance_state.has_identity:
            raise ValueError("Payment.provider é imutável após criação")
        return value
