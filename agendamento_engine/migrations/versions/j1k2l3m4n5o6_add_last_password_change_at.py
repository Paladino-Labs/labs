"""add last_password_change_at to users

Revision ID: j1k2l3m4n5o6
Revises: i1j2k3l4m5n6
Create Date: 2026-05-30

Adiciona coluna last_password_change_at a users.
Usada por get_current_user para invalidar JWTs emitidos antes da troca de senha.
Migration idempotente via ADD COLUMN IF NOT EXISTS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, Sequence[str], None] = "i1j2k3l4m5n6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE users "
        "ADD COLUMN IF NOT EXISTS last_password_change_at TIMESTAMPTZ"
    ))


def downgrade() -> None:
    op.drop_column("users", "last_password_change_at")
