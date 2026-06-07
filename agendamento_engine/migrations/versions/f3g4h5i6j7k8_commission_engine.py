"""commission_engine

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-06-07

Sprint 12 — CommissionEngine:
  1. Nova tabela commission_policies (com RLS)
  2. Nova tabela commission_payouts (com RLS)
  3. Nova tabela commissions (com RLS)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, Sequence[str], None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS commission_policies (
            policy_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            UUID NOT NULL REFERENCES companies(id),
            professional_id       UUID REFERENCES professionals(id),
            service_id            UUID REFERENCES services(id),
            commission_base       VARCHAR NOT NULL,
            commission_fee_policy VARCHAR NOT NULL,
            rate                  NUMERIC(5,2),
            fixed_amount          NUMERIC(10,2),
            CONSTRAINT rate_or_fixed CHECK (
                (rate IS NOT NULL AND fixed_amount IS NULL) OR
                (rate IS NULL AND fixed_amount IS NOT NULL)
            ),
            is_active             BOOLEAN NOT NULL DEFAULT true,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON commission_policies
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE commission_policies ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS commission_payouts (
            payout_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            professional_id   UUID NOT NULL REFERENCES professionals(id),
            total_amount      NUMERIC(10,2) NOT NULL,
            account_id        UUID NOT NULL REFERENCES accounts(account_id),
            status            VARCHAR NOT NULL DEFAULT 'PENDING',
            paid_at           TIMESTAMPTZ,
            created_by        UUID NOT NULL REFERENCES users(id),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON commission_payouts
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE commission_payouts ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS commissions (
            commission_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            professional_id   UUID NOT NULL REFERENCES professionals(id),
            policy_id         UUID REFERENCES commission_policies(policy_id),
            appointment_id    UUID REFERENCES appointments(id),
            operation_type    VARCHAR NOT NULL,
            gross_amount      NUMERIC(10,2) NOT NULL,
            commission_amount NUMERIC(10,2) NOT NULL,
            status            VARCHAR NOT NULL DEFAULT 'CALCULATED',
            due_date          DATE,
            paid_at           TIMESTAMPTZ,
            payout_id         UUID REFERENCES commission_payouts(payout_id),
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON commissions
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE commissions ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS commissions"))
    op.execute(sa.text("DROP TABLE IF EXISTS commission_payouts"))
    op.execute(sa.text("DROP TABLE IF EXISTS commission_policies"))
