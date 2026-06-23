"""vínculo User↔Professional (professionals.user_id + user_invitations.professional_id)

Revision ID: e0s27_professional_user_link
Revises: e0s26_multiitem_packages
Create Date: 2026-06-22

Sprint 27 (backend) — Escopo do papel PROFESSIONAL:
  - professionals.user_id (FK users, nullable, UNIQUE parcial) → vínculo 1:1 opcional
  - user_invitations.professional_id (FK professionals) → linka no aceite do convite
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s27_professional_user_link"
down_revision: Union[str, Sequence[str], None] = "e0s26_multiitem_packages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # FK user_id em professionals (nullable, unique parcial — 1:1 opcional)
    op.execute(sa.text(
        "ALTER TABLE professionals "
        "ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id) ON DELETE SET NULL"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_professionals_user_id "
        "ON professionals (user_id) WHERE user_id IS NOT NULL"
    ))

    # professional_id em user_invitations (para linkar no convite)
    op.execute(sa.text(
        "ALTER TABLE user_invitations "
        "ADD COLUMN IF NOT EXISTS professional_id UUID "
        "REFERENCES professionals(id) ON DELETE SET NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE user_invitations DROP COLUMN IF EXISTS professional_id"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_professionals_user_id"))
    op.execute(sa.text("ALTER TABLE professionals DROP COLUMN IF EXISTS user_id"))
