"""create_products_table

Revision ID: e3c8b5d91a47
Revises: d1a4f7b92c06
Create Date: 2026-04-19

Cria a tabela `products` para itens à venda (produtos de barbearia, etc.).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e3c8b5d91a47'
down_revision: Union[str, Sequence[str], None] = 'd1a4f7b92c06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "products",
        sa.Column("id",          postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id",  postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name",        sa.String(255), nullable=False),
        sa.Column("description", sa.Text(),      nullable=True),
        sa.Column("price",       sa.Numeric(10, 2), nullable=False),
        sa.Column("image_url",   sa.String(500), nullable=True),
        sa.Column("active",      sa.Boolean(),   nullable=False, server_default=sa.true()),
        sa.Column("created_at",  sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at",  sa.TIMESTAMP(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_products_company_id", "products", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_products_company_id", table_name="products")
    op.drop_table("products")
