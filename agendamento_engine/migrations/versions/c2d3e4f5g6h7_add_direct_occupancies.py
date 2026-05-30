"""add_direct_occupancies

Revision ID: c2d3e4f5g6h7
Revises: b2c3d4e5f6g7
Create Date: 2026-05-30

Cria tabela direct_occupancies.
Registra bloqueios manuais de agenda por OWNER/ADMIN/OPERATOR.
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c2d3e4f5g6h7"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6g7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS direct_occupancies (
            occupancy_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            professional_id     UUID NOT NULL REFERENCES professionals(id),
            start_at            TIMESTAMPTZ NOT NULL,
            end_at              TIMESTAMPTZ NOT NULL,
            appointment_id      UUID REFERENCES appointments(id),
            reason              VARCHAR NOT NULL,
            opened_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            closed_at           TIMESTAMPTZ,
            opened_by           UUID NOT NULL REFERENCES users(id)
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON direct_occupancies
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE direct_occupancies ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS direct_occupancies CASCADE"))
