"""product_sales — venda avulsa de produto para retirada

Revision ID: e0s29_product_sales
Revises: e0s28_professional_contact_customer_filter
Create Date: 2026-07-03

Sprint A (produtos):
  - product_sales: venda avulsa de produto p/ retirada na barbearia
    (RESERVED | PURCHASED | PICKED_UP; sem appointment_id por decisão
    de produto). Snapshots de nome/preço/quantidade.
  - RLS canônico app.current_company_id.

Tabela nasce VAZIA (não há produtos vendidos em produção) → backfill zero.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s29_product_sales"
down_revision: Union[str, Sequence[str], None] = "e0s28_professional_contact_customer_filter"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS product_sales (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            customer_id  UUID NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
            product_id   UUID NOT NULL REFERENCES products(id) ON DELETE RESTRICT,
            payment_id   UUID REFERENCES payments(payment_id) ON DELETE SET NULL,
            product_name VARCHAR(255) NOT NULL,
            quantity     INTEGER NOT NULL DEFAULT 1 CHECK (quantity > 0),
            unit_price   NUMERIC(10, 2) NOT NULL,
            total_price  NUMERIC(10, 2) NOT NULL,
            status       VARCHAR(20) NOT NULL DEFAULT 'RESERVED'
                         CHECK (status IN ('RESERVED', 'PURCHASED', 'PICKED_UP')),
            picked_up_at TIMESTAMPTZ,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_product_sales_company_id "
        "ON product_sales (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_product_sales_customer_id "
        "ON product_sales (customer_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_product_sales_status "
        "ON product_sales (status)"
    ))

    # RLS canônico
    op.execute(sa.text("ALTER TABLE product_sales ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON product_sales
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
    op.execute(sa.text("DROP TABLE IF EXISTS product_sales"))
