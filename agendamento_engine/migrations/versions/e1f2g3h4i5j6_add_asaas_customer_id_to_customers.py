"""add asaas_customer_id to customers

Revision ID: e1f2g3h4i5j6
Revises: d1e2f3g4h5i6
Create Date: 2026-06-02

Adiciona coluna asaas_customer_id (nullable) em customers.
Preenchida na primeira cobrança via Asaas — lazy registration.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2g3h4i5j6"
down_revision: Union[str, Sequence[str], None] = "d1e2f3g4h5i6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE customers ADD COLUMN IF NOT EXISTS asaas_customer_id VARCHAR(50)"
    ))


def downgrade() -> None:
    op.drop_column("customers", "asaas_customer_id")
