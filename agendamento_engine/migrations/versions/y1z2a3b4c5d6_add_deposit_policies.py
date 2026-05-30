"""add_deposit_policies

Revision ID: y1z2a3b4c5d6
Revises: x1y2z3a4b5c6
Create Date: 2026-05-30

Cria tabela deposit_policies.
service_id NULL = política global do tenant; preenchido = política por serviço.
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "y1z2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "x1y2z3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS deposit_policies (
            policy_id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                      UUID NOT NULL REFERENCES companies(id),
            service_id                      UUID REFERENCES services(id),
            deposit_type                    VARCHAR NOT NULL,
            deposit_value                   NUMERIC(10,2) NOT NULL,
            refundable_until_hours_before   INTEGER NOT NULL DEFAULT 24,
            refund_on_tenant_fault          BOOLEAN NOT NULL DEFAULT true,
            retain_on_no_show               BOOLEAN NOT NULL DEFAULT true,
            commission_on_retained_deposit  BOOLEAN NOT NULL DEFAULT false,
            created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                      TIMESTAMPTZ
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON deposit_policies
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE deposit_policies ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS deposit_policies CASCADE"))
