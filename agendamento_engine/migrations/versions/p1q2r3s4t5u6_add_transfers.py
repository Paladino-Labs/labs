"""add_transfers

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-05-30

Cria tabela transfers com RLS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p1q2r3s4t5u6"
down_revision: Union[str, Sequence[str], None] = "o1p2q3r4s5t6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS transfers (
            transfer_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            from_account_id     UUID NOT NULL REFERENCES accounts(account_id),
            to_account_id       UUID NOT NULL REFERENCES accounts(account_id),
            amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
            status              VARCHAR NOT NULL DEFAULT 'REQUESTED',
            requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            completed_at        TIMESTAMPTZ,
            failed_at           TIMESTAMPTZ,
            failure_reason      VARCHAR,
            notes               TEXT
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON transfers
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE transfers ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS transfers CASCADE"))
