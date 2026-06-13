"""service_input_checklists — insumos pós-atendimento (Estágio 1+)

Revision ID: e0s25e_service_input_checklists
Revises: e0s25d_operation_professionals
Create Date: 2026-06-13

Sprint 25 — Schema-only (Estágio 1+):
  Checklist de insumos consumidos por serviço (UI do checklist no Estágio 1+).
  SEM endpoint/service/tela neste estágio. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s25e_service_input_checklists"
down_revision: Union[str, Sequence[str], None] = "e0s25d_operation_professionals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS service_input_checklists (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            service_id        UUID NOT NULL REFERENCES services(id),
            product_id        UUID NOT NULL REFERENCES products(id),
            default_quantity  NUMERIC(15,3) NOT NULL DEFAULT 1,
            unit              VARCHAR(20),
            active            BOOLEAN NOT NULL DEFAULT true
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_input_checklists_company_id "
        "ON service_input_checklists (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_service_input_checklists_service_id "
        "ON service_input_checklists (service_id)"
    ))

    op.execute(sa.text("ALTER TABLE service_input_checklists ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON service_input_checklists
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
    op.execute(sa.text("DROP TABLE IF EXISTS service_input_checklists"))
