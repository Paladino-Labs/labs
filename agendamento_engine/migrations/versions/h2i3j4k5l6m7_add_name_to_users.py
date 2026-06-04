"""add_name_to_users

Revision ID: h2i3j4k5l6m7
Revises: g3h4i5j6k7l8
Create Date: 2026-06-04

Adiciona coluna `name` (VARCHAR 100, nullable) à tabela users.
Campo opcional — usuários existentes ficam com name=NULL; frontend usa email como fallback.
"""
from alembic import op
import sqlalchemy as sa

revision = "h2i3j4k5l6m7"
down_revision = "g3h4i5j6k7l8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS name VARCHAR(100)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS name")
