"""add_reconciliation_records

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-05-30

Cria tabela reconciliation_records com RLS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, Sequence[str], None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS reconciliation_records (
            reconciliation_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            account_id          UUID NOT NULL REFERENCES accounts(account_id),
            status              VARCHAR NOT NULL DEFAULT 'OPEN',
            opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at           TIMESTAMPTZ,
            opened_by           UUID NOT NULL REFERENCES users(id),
            closed_by           UUID REFERENCES users(id),
            notes               TEXT
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON reconciliation_records
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE reconciliation_records ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS reconciliation_records CASCADE"))
