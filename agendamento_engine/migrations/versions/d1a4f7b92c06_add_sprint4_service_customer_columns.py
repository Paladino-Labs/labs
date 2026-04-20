"""add_sprint4_service_customer_columns

Revision ID: d1a4f7b92c06
Revises: 906df50dc028
Create Date: 2026-04-19

Adiciona:
  - services.description (TEXT, nullable)
  - services.image_url   (VARCHAR 500, nullable)
  - customers.notes      (TEXT, nullable)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd1a4f7b92c06'
down_revision: Union[str, Sequence[str], None] = '906df50dc028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("services",  sa.Column("description", sa.Text(), nullable=True))
    op.add_column("services",  sa.Column("image_url",   sa.String(500), nullable=True))
    op.add_column("customers", sa.Column("notes",       sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("customers", "notes")
    op.drop_column("services",  "image_url")
    op.drop_column("services",  "description")
