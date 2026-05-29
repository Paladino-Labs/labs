"""sprint4: processed_idempotency_keys

Revision ID: d1e2f3a4b5c6
Revises: c2d3e4f5a6b7
Create Date: 2026-05-27

Tabela de controle de idempotência de consumers de eventos.
PK composta (key, consumer) garante unicidade por fato+consumidor.
company_id é coluna de auditoria — não participa da unicidade (pode ser NULL para eventos de plataforma).
Índice em processed_at para o cleanup worker diário.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processed_idempotency_keys",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("consumer", sa.String(), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("result_summary", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("key", "consumer"),
    )
    op.create_index(
        "ix_processed_idempotency_keys_processed_at",
        "processed_idempotency_keys",
        ["processed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processed_idempotency_keys_processed_at",
        table_name="processed_idempotency_keys",
    )
    op.drop_table("processed_idempotency_keys")
