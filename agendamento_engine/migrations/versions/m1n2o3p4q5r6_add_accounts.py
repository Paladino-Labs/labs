"""add_accounts

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-05-30

Cria tabela accounts com UNIQUE INDEX parcial (COALESCE provider) e RLS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "l1m2n3o4p5q6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS accounts (
            account_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            name                VARCHAR NOT NULL,
            type                VARCHAR NOT NULL,
            provider            VARCHAR,
            external_ref        VARCHAR,
            currency            CHAR(3) NOT NULL DEFAULT 'BRL',
            status              VARCHAR NOT NULL DEFAULT 'ACTIVE',
            is_default_inflow   BOOLEAN NOT NULL DEFAULT false,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ
        )
    """))

    # Constraint correta: partial unique index com COALESCE para NULLs
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_default_inflow_provider
            ON accounts(company_id, COALESCE(provider, '__none__'))
            WHERE is_default_inflow = true
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON accounts
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_default_inflow_provider"))
    op.execute(sa.text("DROP TABLE IF EXISTS accounts CASCADE"))
