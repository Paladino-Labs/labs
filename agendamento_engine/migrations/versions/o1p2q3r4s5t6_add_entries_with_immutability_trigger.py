"""add_entries_with_immutability_trigger

Revision ID: o1p2q3r4s5t6
Revises: n1o2p3q4r5s6
Create Date: 2026-05-30

Cria tabela entries (append-only) com triggers de imutabilidade e RLS.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, Sequence[str], None] = "n1o2p3q4r5s6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS entries (
            entry_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            type                VARCHAR NOT NULL,
            direction           VARCHAR NOT NULL,
            amount              NUMERIC(15,2) NOT NULL CHECK (amount > 0),
            occurred_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            category            VARCHAR NOT NULL,
            source_type         VARCHAR NOT NULL,
            source_id           UUID NOT NULL,
            movement_id         UUID,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_entry_modification()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'entries e append-only: % nao permitido', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """))

    op.execute(sa.text("""
        CREATE TRIGGER entry_no_update
            BEFORE UPDATE ON entries FOR EACH ROW
            EXECUTE FUNCTION prevent_entry_modification()
    """))

    op.execute(sa.text("""
        CREATE TRIGGER entry_no_delete
            BEFORE DELETE ON entries FOR EACH ROW
            EXECUTE FUNCTION prevent_entry_modification()
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON entries
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE entries ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS entry_no_update ON entries"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS entry_no_delete ON entries"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_entry_modification"))
    op.execute(sa.text("DROP TABLE IF EXISTS entries CASCADE"))
