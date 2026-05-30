"""add_tenant_fee_routing_policies

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-05-30

Cria tabela tenant_fee_routing_policies com RLS.
Lookup por (company_id, fee_source) — sem FK em tenant_configs.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS tenant_fee_routing_policies (
            policy_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            fee_source          VARCHAR NOT NULL,
            client_share        NUMERIC(5,2) NOT NULL DEFAULT 0,
            tenant_share        NUMERIC(5,2) NOT NULL DEFAULT 100,
            professional_share  NUMERIC(5,2) NOT NULL DEFAULT 0,
            CONSTRAINT shares_sum_100 CHECK (
                client_share + tenant_share + professional_share = 100
            ),
            UNIQUE(company_id, fee_source),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON tenant_fee_routing_policies
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text(
        "ALTER TABLE tenant_fee_routing_policies ENABLE ROW LEVEL SECURITY"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS tenant_fee_routing_policies CASCADE"))
