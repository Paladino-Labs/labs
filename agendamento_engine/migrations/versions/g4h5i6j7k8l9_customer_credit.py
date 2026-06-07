"""customer_credit

Revision ID: g4h5i6j7k8l9
Revises: f3g4h5i6j7k8
Create Date: 2026-06-07

Sprint 13 — CustomerCredit (Cotas):
  1. Nova tabela customer_credits (com RLS)
  2. Nova tabela customer_credit_consumptions (com RLS)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g4h5i6j7k8l9"
down_revision: Union[str, Sequence[str], None] = "f3g4h5i6j7k8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS customer_credits (
            credit_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            customer_id       UUID NOT NULL REFERENCES customers(id),
            entitlement_type  VARCHAR NOT NULL,
            source_id         UUID,
            total_cotas       INTEGER NOT NULL CHECK (total_cotas > 0),
            remaining_cotas   INTEGER NOT NULL,
            status            VARCHAR NOT NULL DEFAULT 'ACTIVE',
            granted_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at        TIMESTAMPTZ,
            CONSTRAINT remaining_lte_total CHECK (remaining_cotas <= total_cotas),
            CONSTRAINT remaining_gte_zero  CHECK (remaining_cotas >= 0)
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON customer_credits
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE customer_credits ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS customer_credit_consumptions (
            consumption_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            credit_id       UUID NOT NULL REFERENCES customer_credits(credit_id),
            company_id      UUID NOT NULL REFERENCES companies(id),
            customer_id     UUID NOT NULL REFERENCES customers(id),
            appointment_id  UUID REFERENCES appointments(id),
            consumed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON customer_credit_consumptions
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE customer_credit_consumptions ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS customer_credit_consumptions"))
    op.execute(sa.text("DROP TABLE IF EXISTS customer_credits"))
