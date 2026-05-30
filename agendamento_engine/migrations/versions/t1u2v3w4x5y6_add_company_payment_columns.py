"""add_company_payment_columns

Revision ID: t1u2v3w4x5y6
Revises: s1t2u3v4w5x6
Create Date: 2026-05-30

Adiciona colunas de pagamento na tabela companies:
  payment_provider, external_account_id, external_account_status,
  external_account_created_at
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t1u2v3w4x5y6"
down_revision: Union[str, Sequence[str], None] = "s1t2u3v4w5x6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS payment_provider VARCHAR"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_id VARCHAR"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_status VARCHAR"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies ADD COLUMN IF NOT EXISTS external_account_created_at TIMESTAMPTZ"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE companies DROP COLUMN IF EXISTS external_account_created_at"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies DROP COLUMN IF EXISTS external_account_status"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies DROP COLUMN IF EXISTS external_account_id"
    ))
    op.execute(sa.text(
        "ALTER TABLE companies DROP COLUMN IF EXISTS payment_provider"
    ))
