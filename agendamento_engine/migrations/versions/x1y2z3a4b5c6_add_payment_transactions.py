"""add_payment_transactions

Revision ID: x1y2z3a4b5c6
Revises: w1x2y3z4a5b6
Create Date: 2026-05-30

Cria tabela payment_transactions.
UNIQUE(company_id, provider_transaction_id) garante idempotência no banco,
não apenas no código — requisito crítico do Sprint 9.
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "x1y2z3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "w1x2y3z4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payment_transactions (
            transaction_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            payment_id              UUID NOT NULL REFERENCES payments(payment_id),
            company_id              UUID NOT NULL REFERENCES companies(id),
            provider_transaction_id VARCHAR NOT NULL,
            amount                  NUMERIC(15,2) NOT NULL,
            status                  VARCHAR NOT NULL,
            raw_response            JSONB NOT NULL,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE(company_id, provider_transaction_id)
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON payment_transactions
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE payment_transactions ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS payment_transactions CASCADE"))
