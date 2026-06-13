"""operation_professionals — multi-profissional por operação (Estágio 1+)

Revision ID: e0s25d_operation_professionals
Revises: e0s25c_encomenda
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Permite múltiplos profissionais por appointment (PRIMARY|ASSISTANT|OBSERVER).
  SEM endpoint/service/tela neste estágio. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25d_operation_professionals"
down_revision: Union[str, Sequence[str], None] = "e0s25c_encomenda"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS operation_professionals (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            appointment_id   UUID NOT NULL REFERENCES appointments(id),
            company_id       UUID NOT NULL REFERENCES companies(id),
            professional_id  UUID NOT NULL REFERENCES professionals(id),
            -- PRIMARY | ASSISTANT | OBSERVER
            role             VARCHAR(30) NOT NULL DEFAULT 'PRIMARY',
            UNIQUE (appointment_id, professional_id)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_operation_professionals_company_id "
        "ON operation_professionals (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_operation_professionals_appointment_id "
        "ON operation_professionals (appointment_id)"
    ))

    op.execute(sa.text("ALTER TABLE operation_professionals ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON operation_professionals
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
    op.execute(sa.text("DROP TABLE IF EXISTS operation_professionals"))
