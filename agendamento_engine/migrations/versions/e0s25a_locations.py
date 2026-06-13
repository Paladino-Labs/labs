"""locations — localização física para multi-unidade (Estágio 1+)

Revision ID: e0s25a_locations
Revises: e0s27a_conversation_messages
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Estrutura de dados para multi-unidade. SEM endpoint/service/tela neste
  estágio. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25a_locations"
down_revision: Union[str, Sequence[str], None] = "e0s27a_conversation_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS locations (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id),
            name        VARCHAR(255) NOT NULL,
            address     TEXT,
            is_primary  BOOLEAN NOT NULL DEFAULT false,
            active      BOOLEAN NOT NULL DEFAULT true,
            created_at  TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_locations_company_id ON locations (company_id)"
    ))

    op.execute(sa.text("ALTER TABLE locations ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON locations
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS locations"))
