import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class PaymentSourceAuthorization(Base):
    """
    Autorização de método de pagamento por tenant — Sprint D (Portal).

    Tabela de identidade GLOBAL (identity_id, não customer_id): o token do
    provider pertence ao cliente Paladino-wide; cada tenant recebe uma
    autorização explícita com mode ALWAYS | ONCE. RLS habilitado SEM policy
    no banco — acesso exclusivamente via service layer.

    Não confundir com PaymentSource (payment_sources, tenant-scoped, legada).
    """
    __tablename__ = "payment_source_authorizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id = Column(
        UUID(as_uuid=True),
        ForeignKey("paladino_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    source_token = Column(String(255), nullable=False)
    provider = Column(String(20), nullable=False, default="ASAAS")
    mode = Column(String(10), nullable=False)  # ALWAYS | ONCE
    last_four = Column(String(4), nullable=True)
    brand = Column(String(20), nullable=True)
    granted_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    revoked_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "identity_id", "company_id", "source_token",
            name="uq_psa_identity_company_token",
        ),
    )
