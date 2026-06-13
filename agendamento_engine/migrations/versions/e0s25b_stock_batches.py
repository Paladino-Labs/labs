"""stock_batches — lotes de estoque com rastreabilidade e validade (FEFO Estágio 1+)

Revision ID: e0s25b_stock_batches
Revises: e0s25a_locations
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Lote de estoque para rastreabilidade e FEFO (First Expired First Out).
  SEM endpoint/service/tela neste estágio. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25b_stock_batches"
down_revision: Union[str, Sequence[str], None] = "e0s25a_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS stock_batches (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL REFERENCES companies(id),
            product_id    UUID NOT NULL REFERENCES products(id),
            batch_number  VARCHAR(100),
            expiry_date   DATE,                                -- para FEFO
            quantity      NUMERIC(15,3) NOT NULL DEFAULT 0,
            unit_cost     NUMERIC(15,2),
            supplier_id   UUID REFERENCES suppliers(id),
            received_at   DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at    TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_batches_company_id ON stock_batches (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_batches_product_id ON stock_batches (product_id)"
    ))

    op.execute(sa.text("ALTER TABLE stock_batches ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON stock_batches
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS stock_batches"))
