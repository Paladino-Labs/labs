"""fix: políticas RLS Fase 2 (Sprints 6–10) — app.company_id → app.current_company_id

Revision ID: e0s_rls_fix_fase2
Revises: e0s_rls_fix_sprints11_15
Create Date: 2026-06-11

Mesmo bug corrigido em e0s_rls_fix_sprints11_15, agora nas 15 tabelas criadas
pelas migrations da Fase 2 (Sprints 6–10): as políticas tenant_isolation leem
o setting errado (app.company_id) — a aplicação seta app.current_company_id
(core/db_rls.py). Como app.company_id nunca é setado, current_setting(..., TRUE)
retorna NULL e a política negaria TODAS as linhas para um role sem BYPASSRLS.
Hoje mascarado porque o role do Supabase é superuser; uma mudança de role
quebraria o isolamento multi-tenant silenciosamente.

Recria as 15 políticas com o padrão canônico de h1i2j3k4l5m6:
  - setting app.current_company_id
  - bypass via string vazia (PLATFORM_OWNER / workers de plataforma)
  - WITH CHECK explícito
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "e0s_rls_fix_fase2"
down_revision: Union[str, Sequence[str], None] = "e0s_rls_fix_sprints11_15"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Migrations de origem (todas com o padrão incorreto app.company_id):
#   accounts (m1n2o3p4q5r6) · movements (n1o2p3q4r5s6) · entries (o1p2q3r4s5t6)
#   transfers (p1q2r3s4t5u6) · reconciliation_records (q1r2s3t4u5v6)
#   movement_reconciliations (r1s2t3u4v5w6) · cash_counts (s1t2u3v4w5x6)
#   tenant_fee_routing_policies (k1l2m3n4o5p6) · payment_sources (v1w2x3y4z5a6)
#   payments (w1x2y3z4a5b6) · payment_transactions (x1y2z3a4b5c6)
#   deposit_policies (y1z2a3b4c5d6) · schedule_exceptions (a3b4c5d6e7f8)
#   reservations (b2c3d4e5f6g7) · direct_occupancies (c2d3e4f5g6h7)
_AFFECTED_TABLES = [
    "payments",
    "payment_sources",
    "payment_transactions",
    "deposit_policies",
    "transfers",
    "entries",
    "movements",
    "accounts",
    "cash_counts",
    "tenant_fee_routing_policies",
    "movement_reconciliations",
    "reconciliation_records",
    "direct_occupancies",
    "schedule_exceptions",
    "reservations",
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
