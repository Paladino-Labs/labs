"""sprint2_user_company_id_nullable

Torna users.company_id nullable para suportar PLATFORM_OWNER (sem tenant).

Revision ID: b1c2d3e4f5a6
Revises: a9b1c2d3e4f5
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a9b1c2d3e4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "company_id", nullable=True)


def downgrade() -> None:
    # Reverter exige que nenhuma linha tenha company_id NULL.
    op.alter_column("users", "company_id", nullable=False)
