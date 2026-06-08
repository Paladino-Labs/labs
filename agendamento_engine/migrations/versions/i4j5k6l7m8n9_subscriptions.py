"""subscriptions

Revision ID: i4j5k6l7m8n9
Revises: h3i4j5k6l7m8
Create Date: 2026-06-08

Sprint 15 — Assinaturas:
  1. Nova tabela subscription_plans (com RLS)
  2. Nova tabela customer_subscriptions (com RLS)
  3. ALTER TABLE payments ADD COLUMN subscription_id
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i4j5k6l7m8n9"
down_revision: Union[str, Sequence[str], None] = "h3i4j5k6l7m8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS subscription_plans (
            plan_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            name              VARCHAR NOT NULL,
            service_id        UUID REFERENCES services(id),
            cotas_per_cycle   INTEGER NOT NULL CHECK (cotas_per_cycle > 0),
            price             NUMERIC(10,2) NOT NULL CHECK (price >= 0),
            cycle_days        INTEGER NOT NULL DEFAULT 30,
            rollover_enabled  BOOLEAN NOT NULL DEFAULT false,
            is_active         BOOLEAN NOT NULL DEFAULT true,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON subscription_plans
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE subscription_plans ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS customer_subscriptions (
            subscription_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            customer_id       UUID NOT NULL REFERENCES customers(id),
            plan_id           UUID NOT NULL REFERENCES subscription_plans(plan_id),
            status            VARCHAR NOT NULL DEFAULT 'ACTIVE',
            next_billing_at   TIMESTAMPTZ NOT NULL,
            overdue_since     TIMESTAMPTZ,
            paused_at         TIMESTAMPTZ,
            cancelled_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON customer_subscriptions
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE customer_subscriptions ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        ALTER TABLE payments
            ADD COLUMN IF NOT EXISTS subscription_id UUID
            REFERENCES customer_subscriptions(subscription_id)
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE payments DROP COLUMN IF EXISTS subscription_id"))
    op.execute(sa.text("DROP TABLE IF EXISTS customer_subscriptions"))
    op.execute(sa.text("DROP TABLE IF EXISTS subscription_plans"))
