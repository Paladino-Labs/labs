"""waitlist_configs + waitlist_entries

Revision ID: e0sG2_waitlist
Revises: e0sG1_nps
Create Date: 2026-06-12

Sprint G — Fila de espera orientada a eventos:
  1. waitlist_configs — configuração por tenant (1:1): prioridade
     (FIFO | PRIORITY_MANUAL) e janela mínima de notificação
  2. waitlist_entries — entrada na fila com escopo
     SERVICE | PROFESSIONAL | PRODUCT (apenas 1 dos 3 FKs preenchido,
     CHECK constraint); status WAITING | NOTIFIED | BOOKED | EXPIRED |
     CANCELLED; notificação NÃO reserva o slot (primeiro a agir leva)
Ambas com RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sG2_waitlist"
down_revision: Union[str, Sequence[str], None] = "e0sG1_nps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ["waitlist_configs", "waitlist_entries"]


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
    # 1. waitlist_configs
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS waitlist_configs (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                  UUID NOT NULL UNIQUE REFERENCES companies(id),
            enabled                     BOOLEAN NOT NULL DEFAULT true,
            priority_mode               VARCHAR(20) NOT NULL DEFAULT 'FIFO',
            notification_window_hours   INTEGER NOT NULL DEFAULT 2,
            created_at                  TIMESTAMPTZ DEFAULT now()
        )
    """))

    # 2. waitlist_entries
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS waitlist_entries (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id),
            customer_id      UUID NOT NULL REFERENCES customers(id),
            scope_type       VARCHAR(20) NOT NULL,
            service_id       UUID REFERENCES services(id),
            professional_id  UUID REFERENCES professionals(id),
            product_id       UUID REFERENCES products(id),
            status           VARCHAR(20) NOT NULL DEFAULT 'WAITING',
            priority         INTEGER NOT NULL DEFAULT 0,
            source_channel   VARCHAR(20) NOT NULL DEFAULT 'PAINEL',
            notified_at      TIMESTAMPTZ,
            expires_at       TIMESTAMPTZ,
            created_at       TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT check_waitlist_scope CHECK (
                (scope_type = 'SERVICE'      AND service_id IS NOT NULL
                    AND professional_id IS NULL AND product_id IS NULL)
                OR (scope_type = 'PROFESSIONAL' AND professional_id IS NOT NULL
                    AND service_id IS NULL AND product_id IS NULL)
                OR (scope_type = 'PRODUCT'   AND product_id IS NOT NULL
                    AND service_id IS NULL AND professional_id IS NULL)
            )
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_waitlist_entries_company_id "
        "ON waitlist_entries (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_waitlist_entries_scope "
        "ON waitlist_entries (company_id, scope_type, service_id, "
        "professional_id, product_id, status)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_waitlist_entries_status_expires "
        "ON waitlist_entries (status, expires_at)"
    ))

    for table in _NEW_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
