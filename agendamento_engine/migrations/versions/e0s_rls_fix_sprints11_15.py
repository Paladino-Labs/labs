"""fix: políticas RLS Sprints 11–15 — app.company_id → app.current_company_id

Revision ID: e0s_rls_fix_sprints11_15
Revises: e0s18a_expenses
Create Date: 2026-06-11

As migrations dos Sprints 11–15 criaram políticas tenant_isolation lendo o
setting errado (app.company_id) — a aplicação seta app.current_company_id
(core/db_rls.py). Como app.company_id nunca é setado, current_setting(..., TRUE)
retorna NULL e a política negaria TODAS as linhas para um role sem BYPASSRLS.
Hoje mascarado porque o role do Supabase é superuser; uma mudança de role
quebraria o isolamento multi-tenant silenciosamente.

Recria as 11 políticas com o padrão canônico de h1i2j3k4l5m6:
  - setting app.current_company_id
  - bypass via string vazia (PLATFORM_OWNER / workers de plataforma)
  - WITH CHECK explícito
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "e0s_rls_fix_sprints11_15"
down_revision: Union[str, Sequence[str], None] = "e0s18a_expenses"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Sprint 11 (e2f3g4h5i6j7) · 12 (f3g4h5i6j7k8) · 13 (g4h5i6j7k8l9)
# Sprint 14 (h3i4j5k6l7m8) · 15 (i4j5k6l7m8n9)
_AFFECTED_TABLES = [
    "service_pricing_overrides",
    "service_variants",
    "commission_policies",
    "commission_payouts",
    "commissions",
    "customer_credits",
    "customer_credit_consumptions",
    "packages",
    "package_purchases",
    "subscription_plans",
    "customer_subscriptions",
]


def upgrade() -> None:
    op.execute(text("SET LOCAL row_security = off"))

    for table in _AFFECTED_TABLES:
        op.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(text(f"""
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
    op.execute(text("SET LOCAL row_security = off"))

    # Recria as políticas com o setting incorreto original (app.company_id),
    # apenas para reversibilidade fiel ao estado anterior.
    for table in _AFFECTED_TABLES:
        op.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(text(f"""
            CREATE POLICY tenant_isolation ON {table}
                USING (company_id = current_setting('app.company_id', TRUE)::UUID)
        """))
