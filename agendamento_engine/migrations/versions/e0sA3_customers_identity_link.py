"""customers.identity_id — vínculo aditivo com paladino_identities

Revision ID: e0sA3_customers_identity_link
Revises: e0sA2_consent_records
Create Date: 2026-06-11

Sprint A — Identidade Paladino (3/3):
  Coluna nullable — não quebra clientes existentes (Decisão D4, aditiva).
  Backfill NÃO acontece aqui: scripts/backfill_identity.py roda em
  janela de manutenção após o deploy (volume pode ser alto; migrations
  devem ser rápidas).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sA3_customers_identity_link"
down_revision: Union[str, Sequence[str], None] = "e0sA2_consent_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE customers "
        "ADD COLUMN IF NOT EXISTS identity_id UUID "
        "REFERENCES paladino_identities(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_customers_identity_id "
        "ON customers (identity_id) WHERE identity_id IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_customers_identity_id"))
    op.execute(sa.text(
        "ALTER TABLE customers DROP COLUMN IF EXISTS identity_id"
    ))
