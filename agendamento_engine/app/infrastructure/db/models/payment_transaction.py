import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class PaymentTransaction(Base):
    """Transação de pagamento — registro de cada evento de confirmação do provider.

    UNIQUE(company_id, provider_transaction_id) garante idempotência no banco:
    tentativas duplicadas de INSERT levantam IntegrityError que confirm() captura.
    """
    __tablename__ = "payment_transactions"
    __table_args__ = (
        UniqueConstraint("company_id", "provider_transaction_id",
                         name="uq_payment_transaction_provider"),
    )

    transaction_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.payment_id"), nullable=False, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    provider_transaction_id = Column(String, nullable=False)
    amount = Column(Numeric(15, 2), nullable=False)
    status = Column(String(50), nullable=False)
    raw_response = Column(JSONB, nullable=False)
    created_at = Column(sa.TIMESTAMP(timezone=True), nullable=False,
                        default=lambda: datetime.now(timezone.utc))
