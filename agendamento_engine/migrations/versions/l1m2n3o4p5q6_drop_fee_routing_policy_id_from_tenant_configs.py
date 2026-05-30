"""drop_fee_routing_policy_id_from_tenant_configs

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-05-30

Remove o placeholder UUID fee_routing_policy_id de tenant_configs
(existia sem FK real — lookup passa a ser por (company_id, fee_source)
em tenant_fee_routing_policies).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE tenant_configs DROP COLUMN IF EXISTS fee_routing_policy_id"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE tenant_configs "
        "ADD COLUMN IF NOT EXISTS fee_routing_policy_id UUID"
    ))
