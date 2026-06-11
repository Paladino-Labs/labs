"""stock + suppliers + payables

Revision ID: e0s17a_stock_suppliers_payables
Revises: e0s_rls_fix_fase2
Create Date: 2026-06-11

Sprint 17 — Estoque + Fornecedores + Payables:
  1. products: + stock_min_alert, unit, avg_cost (NÃO recria stock — já existe)
  2. tenant_configs: + allow_negative_stock (default false = estoque controlado)
  3. Tabelas suppliers, supplier_orders, stock_movements, payables,
     payable_installments — todas com RLS canônico app.current_company_id
  4. FK expenses.supplier_id → suppliers (coluna criada sem FK no Sprint 18)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s17a_stock_suppliers_payables"
down_revision: Union[str, Sequence[str], None] = "e0s_rls_fix_fase2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = [
    "suppliers",
    "supplier_orders",
    "stock_movements",
    "payables",
    "payable_installments",
]


def _enable_rls(table: str) -> None:
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


def upgrade() -> None:
    # 1. products: campos novos (stock já existe — não recriar)
    op.execute(sa.text("""
        ALTER TABLE products
          ADD COLUMN IF NOT EXISTS stock_min_alert NUMERIC(15,2),
          ADD COLUMN IF NOT EXISTS unit VARCHAR(20) DEFAULT 'un',
          ADD COLUMN IF NOT EXISTS avg_cost NUMERIC(15,2)
    """))

    # 2. tenant_configs: controle de estoque negativo (default: controlado)
    op.execute(sa.text("""
        ALTER TABLE tenant_configs
          ADD COLUMN IF NOT EXISTS allow_negative_stock BOOLEAN NOT NULL DEFAULT false
    """))

    # 3. suppliers
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS suppliers (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id),
            name        VARCHAR(255) NOT NULL,
            contact     VARCHAR(255),
            document    VARCHAR(20),
            active      BOOLEAN NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_suppliers_company_id ON suppliers (company_id)"
    ))

    # 4. supplier_orders
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS supplier_orders (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id   UUID NOT NULL REFERENCES companies(id),
            supplier_id  UUID REFERENCES suppliers(id),
            status       VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            ordered_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            received_at  TIMESTAMPTZ,
            notes        TEXT,
            created_by   UUID NOT NULL REFERENCES users(id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_supplier_orders_company_id "
        "ON supplier_orders (company_id)"
    ))

    # 5. stock_movements
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS stock_movements (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id     UUID NOT NULL REFERENCES companies(id),
            product_id     UUID NOT NULL REFERENCES products(id),
            movement_type  VARCHAR(30) NOT NULL,
            quantity       NUMERIC(15,3) NOT NULL,
            unit_cost      NUMERIC(15,2),
            source_type    VARCHAR(30),
            source_id      UUID,
            notes          TEXT,
            occurred_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_by     UUID NOT NULL REFERENCES users(id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_movements_company_id "
        "ON stock_movements (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_stock_movements_company_product "
        "ON stock_movements (company_id, product_id, occurred_at)"
    ))

    # 6. payables
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payables (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id),
            supplier_id     UUID REFERENCES suppliers(id),
            description     VARCHAR(255) NOT NULL,
            total_amount    NUMERIC(15,2) NOT NULL,
            paid_amount     NUMERIC(15,2) NOT NULL DEFAULT 0,
            status          VARCHAR(20) NOT NULL DEFAULT 'OPEN',
            due_date        DATE,
            closing_method  VARCHAR(20) NOT NULL DEFAULT 'CASH_AT_CREATION',
            source_type     VARCHAR(30) NOT NULL,
            source_id       UUID,
            created_by      UUID NOT NULL REFERENCES users(id),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_payables_company_id ON payables (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_payables_company_status_due "
        "ON payables (company_id, status, due_date)"
    ))

    # 7. payable_installments
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payable_installments (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            payable_id          UUID NOT NULL REFERENCES payables(id),
            company_id          UUID NOT NULL REFERENCES companies(id),
            amount              NUMERIC(15,2) NOT NULL,
            due_date            DATE,
            paid_at             TIMESTAMPTZ,
            payment_id          UUID REFERENCES payments(payment_id),
            installment_number  INTEGER NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'OPEN'
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_payable_installments_company_id "
        "ON payable_installments (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_payable_installments_payable "
        "ON payable_installments (payable_id)"
    ))

    for table in _NEW_TABLES:
        _enable_rls(table)

    # 8. FK expenses.supplier_id → suppliers (coluna existe desde o Sprint 18)
    op.execute(sa.text("""
        ALTER TABLE expenses
          ADD CONSTRAINT fk_expenses_supplier
          FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
          ON DELETE SET NULL
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE expenses DROP CONSTRAINT IF EXISTS fk_expenses_supplier"))
    op.execute(sa.text("DROP TABLE IF EXISTS payable_installments"))
    op.execute(sa.text("DROP TABLE IF EXISTS payables"))
    op.execute(sa.text("DROP TABLE IF EXISTS stock_movements"))
    op.execute(sa.text("DROP TABLE IF EXISTS supplier_orders"))
    op.execute(sa.text("DROP TABLE IF EXISTS suppliers"))
    op.execute(sa.text("ALTER TABLE tenant_configs DROP COLUMN IF EXISTS allow_negative_stock"))
    op.execute(sa.text("""
        ALTER TABLE products
          DROP COLUMN IF EXISTS stock_min_alert,
          DROP COLUMN IF EXISTS unit,
          DROP COLUMN IF EXISTS avg_cost
    """))
