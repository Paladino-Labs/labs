import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class Account(Base):
    """Conta financeira do tenant.

    Tipos: CAIXA | ACQUIRER | BANK | ESCROW
    Unicidade de is_default_inflow: UNIQUE INDEX parcial com COALESCE(provider, '__none__')
    """
    __tablename__ = "accounts"

    account_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)          # CAIXA | ACQUIRER | BANK | ESCROW
    provider = Column(String, nullable=True)       # ex: "asaas"
    external_ref = Column(String, nullable=True)
    currency = Column(String(3), nullable=False, default="BRL")
    status = Column(String, nullable=False, default="ACTIVE")
    is_default_inflow = Column(Boolean, nullable=False, default=False)

    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
