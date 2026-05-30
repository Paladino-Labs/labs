"""add_movement_reconciliations

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-05-30

Cria tabela movement_reconciliations (vínculo Many-to-Many entre Movement e
ReconciliationRecord). company_id desnormalizado para RLS sem JOIN.
Movement permanece 100% append-only.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "r1s2t3u4v5w6"
down_revision: Union[str, Sequence[str], None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS movement_reconciliations (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            movement_id         UUID NOT NULL REFERENCES movements(movement_id),
            reconciliation_id   UUID NOT NULL REFERENCES reconciliation_records(reconciliation_id),
            reconciled_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            reconciled_by       UUID NOT NULL REFERENCES users(id),
            UNIQUE(movement_id, reconciliation_id)
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON movement_reconciliations
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE movement_reconciliations ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS movement_reconciliations CASCADE"))
