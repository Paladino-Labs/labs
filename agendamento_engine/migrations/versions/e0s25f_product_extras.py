"""product_extras — barcode + location_id em products (Estágio 1+)

Revision ID: e0s25f_product_extras
Revises: e0s25e_service_input_checklists
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Campos extras de produto: código de barras e vínculo opcional com location.
  SEM endpoint/service/tela neste estágio (colunas apenas).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25f_product_extras"
down_revision: Union[str, Sequence[str], None] = "e0s25e_service_input_checklists"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE products
          ADD COLUMN IF NOT EXISTS barcode VARCHAR(100),
          ADD COLUMN IF NOT EXISTS location_id UUID
            REFERENCES locations(id) ON DELETE SET NULL
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_products_barcode
          ON products (barcode) WHERE barcode IS NOT NULL
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_products_barcode"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS location_id"))
    op.execute(sa.text("ALTER TABLE products DROP COLUMN IF EXISTS barcode"))
