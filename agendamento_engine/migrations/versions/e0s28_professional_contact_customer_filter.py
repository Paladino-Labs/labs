"""email/phone em professionals (filtro de clientes por profissional é só de aplicação)

Revision ID: e0s28_professional_contact_customer_filter
Revises: e0s27_professional_user_link
Create Date: 2026-06-23

Sprint 28 (backend complementar):
  - professionals.email (VARCHAR 255, nullable)
  - professionals.phone (VARCHAR 20, nullable — E.164, ex.: +5562999999999)
  Ambos nullable: profissionais existentes ficam sem dados de contato.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s28_professional_contact_customer_filter"
down_revision: Union[str, Sequence[str], None] = "e0s27_professional_user_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE professionals "
        "ADD COLUMN IF NOT EXISTS email VARCHAR(255), "
        "ADD COLUMN IF NOT EXISTS phone VARCHAR(20)"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE professionals "
        "DROP COLUMN IF EXISTS phone, "
        "DROP COLUMN IF EXISTS email"
    ))
