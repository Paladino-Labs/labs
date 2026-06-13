"""encomenda_orders + encomenda_items — pedido de encomenda com FSM (Estágio 1+)

Revision ID: e0s25c_encomenda
Revises: e0s25b_stock_batches
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Pedido de encomenda com FSM (DRAFT|CONFIRMED|IN_PRODUCTION|READY|DELIVERED|
  CANCELLED) e seus itens. SEM endpoint/service/tela neste estágio.
  RLS canônico app.current_company_id em ambas as tabelas.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25c_encomenda"
down_revision: Union[str, Sequence[str], None] = "e0s25b_stock_batches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS encomenda_orders (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id),
            customer_id    UUID NOT NULL REFERENCES customers(id),
            -- DRAFT | CONFIRMED | IN_PRODUCTION | READY | DELIVERED | CANCELLED
            status         VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            scheduled_for  DATE,
            notes          TEXT,
            created_by     UUID NOT NULL REFERENCES users(id),
            created_at     TIMESTAMPTZ DEFAULT now(),
            updated_at     TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_encomenda_orders_company_id ON encomenda_orders (company_id)"
    ))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS encomenda_items (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id     UUID NOT NULL REFERENCES encomenda_orders(id),
            company_id   UUID NOT NULL REFERENCES companies(id),
            product_id   UUID REFERENCES products(id),
            service_id   UUID REFERENCES services(id),
            description  VARCHAR(500),
            quantity     NUMERIC(15,3) NOT NULL DEFAULT 1,
            unit_price   NUMERIC(15,2) NOT NULL
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_encomenda_items_order_id ON encomenda_items (order_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_encomenda_items_company_id ON encomenda_items (company_id)"
    ))

    for table in ("encomenda_orders", "encomenda_items"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(sa.text(f"""
            CREATE POLICY tenant_isolation ON {table}
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
    op.execute(sa.text("DROP TABLE IF EXISTS encomenda_items"))
    op.execute(sa.text("DROP TABLE IF EXISTS encomenda_orders"))
