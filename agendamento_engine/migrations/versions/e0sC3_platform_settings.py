"""platform_settings — flags e configurações globais da plataforma

Revision ID: e0sC3_platform_settings
Revises: e0sC2_impersonation_grants
Create Date: 2026-06-12

Sprint C — Painel Owner Paladino (3/3):
  Key/value JSONB global. Tabela de PLATAFORMA — sem RLS por tenant;
  acesso exclusivamente via service layer (endpoints exigem PLATFORM_OWNER).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sC3_platform_settings"
down_revision: Union[str, Sequence[str], None] = "e0sC2_impersonation_grants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            key         VARCHAR(100) PRIMARY KEY,
            value       JSONB NOT NULL,
            updated_by  UUID NOT NULL REFERENCES users(id),
            updated_at  TIMESTAMPTZ DEFAULT now()
        )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS platform_settings"))
