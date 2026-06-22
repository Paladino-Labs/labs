"""multi-item packages + plans + service_id/product_id em customer_credits

Revision ID: e0s26_multiitem_packages
Revises: e0s25f_product_extras
Create Date: 2026-06-22

Sprint 26 — Pacotes e assinaturas multi-item:
  1a. package_items (1 pacote → N itens SERVICE/PRODUCT)
  1b. plan_items   (1 plano  → N itens SERVICE/PRODUCT)
  1c. Remove service_id de packages e subscription_plans (substituído por itens)
  1d. service_id/product_id em customer_credits (cota aponta direto p/ alvo)
  1e. RLS canônico app.current_company_id nas novas tabelas

Produção VAZIA nestes domínios → DROP/ALTER sem risco de dados.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s26_multiitem_packages"
down_revision: Union[str, Sequence[str], None] = "e0s25f_product_extras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ["package_items", "plan_items"]


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
    # 1a. package_items
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS package_items (
            item_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            package_id    UUID NOT NULL REFERENCES packages(package_id) ON DELETE CASCADE,
            company_id    UUID NOT NULL REFERENCES companies(id),
            item_type     VARCHAR(10) NOT NULL CHECK (item_type IN ('SERVICE','PRODUCT')),
            service_id    UUID REFERENCES services(id) ON DELETE SET NULL,
            product_id    UUID REFERENCES products(id) ON DELETE SET NULL,
            quantity      INTEGER NOT NULL CHECK (quantity > 0),
            display_order INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT chk_package_item_target CHECK (
                (item_type = 'SERVICE' AND service_id IS NOT NULL AND product_id IS NULL) OR
                (item_type = 'PRODUCT' AND product_id IS NOT NULL AND service_id IS NULL)
            )
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_package_items_package_id "
        "ON package_items (package_id)"
    ))

    # 1b. plan_items
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS plan_items (
            item_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            plan_id       UUID NOT NULL REFERENCES subscription_plans(plan_id) ON DELETE CASCADE,
            company_id    UUID NOT NULL REFERENCES companies(id),
            item_type     VARCHAR(10) NOT NULL CHECK (item_type IN ('SERVICE','PRODUCT')),
            service_id    UUID REFERENCES services(id) ON DELETE SET NULL,
            product_id    UUID REFERENCES products(id) ON DELETE SET NULL,
            quantity      INTEGER NOT NULL CHECK (quantity > 0),
            display_order INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT chk_plan_item_target CHECK (
                (item_type = 'SERVICE' AND service_id IS NOT NULL AND product_id IS NULL) OR
                (item_type = 'PRODUCT' AND product_id IS NOT NULL AND service_id IS NULL)
            )
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_plan_items_plan_id "
        "ON plan_items (plan_id)"
    ))

    # 1c. Remove service_id (substituído por itens)
    op.execute(sa.text("ALTER TABLE packages           DROP COLUMN IF EXISTS service_id"))
    op.execute(sa.text("ALTER TABLE subscription_plans DROP COLUMN IF EXISTS service_id"))

    # 1d. service_id/product_id direto na cota
    op.execute(sa.text("""
        ALTER TABLE customer_credits
            ADD COLUMN IF NOT EXISTS service_id UUID REFERENCES services(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS product_id UUID REFERENCES products(id) ON DELETE SET NULL
    """))

    # 1e. RLS nas novas tabelas
    for table in _NEW_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE customer_credits
            DROP COLUMN IF EXISTS product_id,
            DROP COLUMN IF EXISTS service_id
    """))
    op.execute(sa.text(
        "ALTER TABLE subscription_plans "
        "ADD COLUMN IF NOT EXISTS service_id UUID REFERENCES services(id)"
    ))
    op.execute(sa.text(
        "ALTER TABLE packages "
        "ADD COLUMN IF NOT EXISTS service_id UUID REFERENCES services(id)"
    ))
    op.execute(sa.text("DROP TABLE IF EXISTS plan_items"))
    op.execute(sa.text("DROP TABLE IF EXISTS package_items"))
