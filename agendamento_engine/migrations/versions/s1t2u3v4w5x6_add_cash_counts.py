"""add_cash_counts

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-05-30

Cria tabela cash_counts com RLS.
discrepancy é computado na service layer (counted_amount - expected_amount via compute_balance).
entry_id aponta para a Entry AJUSTE criada quando resolution=ADJUSTED.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "s1t2u3v4w5x6"
down_revision: Union[str, Sequence[str], None] = "r1s2t3u4v5w6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS cash_counts (
            cash_count_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            account_id          UUID NOT NULL REFERENCES accounts(account_id),
            expected_amount     NUMERIC(15,2) NOT NULL,
            counted_amount      NUMERIC(15,2) NOT NULL,
            discrepancy         NUMERIC(15,2) NOT NULL,
            resolution          VARCHAR NOT NULL,
            notes               TEXT,
            entry_id            UUID REFERENCES entries(entry_id),
            created_by          UUID NOT NULL REFERENCES users(id),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON cash_counts
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE cash_counts ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS cash_counts CASCADE"))
