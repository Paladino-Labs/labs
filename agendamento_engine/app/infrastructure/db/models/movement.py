import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, String, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import validates

from app.infrastructure.db.base import Base

# Campos imutáveis após persistência (defesa em profundidade além do trigger de banco)
_IMMUTABLE_FIELDS = {"amount", "type", "account_id", "source_type", "source_id"}


class Movement(Base):
    """Movimento de caixa — 100% append-only.

    Imutabilidade garantida em dois níveis:
      1. Triggers de banco (prevent_movement_modification) — UPDATE/DELETE rejeitados.
      2. @validates ORM — levanta ValueError ao tentar alterar campos após flush().

    Tipos: INFLOW | OUTFLOW | TRANSFER_IN | TRANSFER_OUT
    """
    __tablename__ = "movements"

    movement_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    account_id = Column(
        UUID(as_uuid=True),
        ForeignKey("accounts.account_id"),
        nullable=False,
    )
    type = Column(String, nullable=False)          # INFLOW | OUTFLOW | TRANSFER_IN | TRANSFER_OUT
    amount = Column(Numeric(15, 2), nullable=False)
    occurred_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    source_type = Column(String, nullable=False)
    source_id = Column(UUID(as_uuid=True), nullable=False)
    transfer_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── @validates: defesa em profundidade ────────────────────────────────────

    @validates("amount", "type", "account_id", "source_type", "source_id")
    def validate_immutable(self, key: str, value):
        """Rejeita mutação de campos críticos após a instância ter identidade no banco."""
        if self._sa_instance_state.has_identity:
            raise ValueError(
                f"Movement.{key} é imutável após persistência"
            )
        return value
