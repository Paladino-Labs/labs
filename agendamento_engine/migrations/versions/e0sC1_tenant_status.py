"""companies.status — lifecycle do tenant na plataforma

Revision ID: e0sC1_tenant_status
Revises: e0sD2_payment_source_authorizations
Create Date: 2026-06-12

Sprint C — Painel Owner Paladino (1/3):
  TRIAL | ACTIVE | SUSPENDED | CHURNED.
  Tenants existentes nascem como ACTIVE (default).
  SUSPENDED bloqueia login de usuários do tenant (preserva dados);
  PLATFORM_OWNER (company_id NULL) nunca é bloqueado.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sC1_tenant_status"
down_revision: Union[str, Sequence[str], None] = "e0sD2_payment_source_authorizations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE companies "
        "ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_companies_status ON companies (status)"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS idx_companies_status"))
    op.execute(sa.text("ALTER TABLE companies DROP COLUMN IF EXISTS status"))
