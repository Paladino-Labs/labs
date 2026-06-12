"""crm_configs + customer_classifications + customers.custom_fields

Revision ID: e0sH1_crm
Revises: e0sG2_waitlist
Create Date: 2026-06-12

Sprint H — CRM básico:
  1. crm_configs — thresholds de classificação por tenant (1:1)
  2. customer_classifications — append por recomputação (histórico
     preservado); classificação atual = linha mais recente por customer
  3. customers.custom_fields JSONB (notes já existia — IF NOT EXISTS)
Tabelas novas com RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sH1_crm"
down_revision: Union[str, Sequence[str], None] = "e0sG2_waitlist"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ["crm_configs", "customer_classifications"]


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
    # 1. crm_configs — thresholds customizáveis por tenant
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS crm_configs (
            id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id              UUID NOT NULL UNIQUE REFERENCES companies(id),
            -- NOVO: 1ª operação há <= X dias
            new_customer_days       INTEGER NOT NULL DEFAULT 30,
            -- FREQUENTE: >= N visitas em M meses
            frequent_min_visits     INTEGER NOT NULL DEFAULT 3,
            frequent_period_months  INTEGER NOT NULL DEFAULT 3,
            -- EM_RISCO: sem operação > X × frequência média (mínimo risk_min_days)
            risk_multiplier         NUMERIC(3,1) NOT NULL DEFAULT 2.0,
            risk_min_days           INTEGER NOT NULL DEFAULT 45,
            -- VIP: >= N visitas E >= R$ gasto total
            vip_min_visits          INTEGER NOT NULL DEFAULT 10,
            vip_min_spend           NUMERIC(15,2) NOT NULL DEFAULT 500.00,
            created_at              TIMESTAMPTZ DEFAULT now(),
            updated_at              TIMESTAMPTZ DEFAULT now()
        )
    """))

    # 2. customer_classifications — append por recomputação
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS customer_classifications (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            customer_id       UUID NOT NULL REFERENCES customers(id),
            -- NOVO | FREQUENTE | VIP | EM_RISCO | RECUPERADO | REGULAR
            classification    VARCHAR(20) NOT NULL,
            computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- {visit_count, avg_ticket, days_since_last_visit,
            --  avg_frequency_days, total_spend}
            metrics_snapshot  JSONB NOT NULL DEFAULT '{}'
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_customer_classifications_current
          ON customer_classifications (company_id, customer_id, computed_at DESC)
    """))

    for table in _NEW_TABLES:
        _enable_rls(table)

    # 3. customers: custom_fields (novo) + notes (já existe — no-op seguro)
    op.execute(sa.text("""
        ALTER TABLE customers
          ADD COLUMN IF NOT EXISTS custom_fields JSONB NOT NULL DEFAULT '{}'
    """))
    op.execute(sa.text("""
        ALTER TABLE customers
          ADD COLUMN IF NOT EXISTS notes TEXT
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE customers DROP COLUMN IF EXISTS custom_fields"))
    # notes NÃO é removido — existia antes desta migration
    for table in reversed(_NEW_TABLES):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
