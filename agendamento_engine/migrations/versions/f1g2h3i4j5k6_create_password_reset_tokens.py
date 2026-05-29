"""create_password_reset_tokens

Revision ID: f1g2h3i4j5k6
Revises: e2f6h3i4j5k6
Create Date: 2026-05-28

Cria a tabela password_reset_tokens para o fluxo forgot-password / reset-password.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f1g2h3i4j5k6"
down_revision: Union[str, Sequence[str], None] = "e2f6h3i4j5k6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = inspector.get_table_names()

    if "password_reset_tokens" in existing:
        return

    op.create_table(
        "password_reset_tokens",
        sa.Column(
            "token_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.VARCHAR(255), nullable=False, unique=True),
        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
        ),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_password_reset_tokens_user_id", table_name="password_reset_tokens")
    op.drop_table("password_reset_tokens")
