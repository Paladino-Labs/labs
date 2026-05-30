"""add_movements_with_immutability_trigger

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-05-30

Cria tabela movements (100% append-only) com triggers de imutabilidade e RLS.
Sem colunas de reconciliação — reconciliação via movement_reconciliations (Sprint 7).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS movements (
            movement_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            account_id          UUID NOT NULL REFERENCES accounts(account_id),
            type                VARCHAR NOT NULL,
            amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
            occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            source_type         VARCHAR NOT NULL,
            source_id           UUID NOT NULL,
            transfer_id         UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_movement_modification()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'movements e append-only: % nao permitido', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """))

    op.execute(sa.text("""
        CREATE TRIGGER movement_no_update
            BEFORE UPDATE ON movements FOR EACH ROW
            EXECUTE FUNCTION prevent_movement_modification()
    """))

    op.execute(sa.text("""
        CREATE TRIGGER movement_no_delete
            BEFORE DELETE ON movements FOR EACH ROW
            EXECUTE FUNCTION prevent_movement_modification()
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON movements
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE movements ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS movement_no_update ON movements"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS movement_no_delete ON movements"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_movement_modification"))
    op.execute(sa.text("DROP TABLE IF EXISTS movements CASCADE"))
