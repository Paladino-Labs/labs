"""add_reservations

Revision ID: b2c3d4e5f6g7
Revises: a3b4c5d6e7f8
Create Date: 2026-05-30

Cria tabela reservations com EXCLUDE USING gist (tstzrange).
SOFT | FIRME (type imutável após criação).
ACTIVE | EXPIRED | CANCELLED | PROMOTED | RELEASED | CONSUMED | NO_SHOW.
EXCLUDE cobre SOFT e FIRME enquanto status = 'ACTIVE'.
Requer extensão btree_gist ativa (já habilitada para appointments).
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6g7"
down_revision: Union[str, Sequence[str], None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS reservations (
            reservation_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            professional_id     UUID NOT NULL REFERENCES professionals(id),
            start_at            TIMESTAMPTZ NOT NULL,
            end_at              TIMESTAMPTZ NOT NULL,
            type                VARCHAR NOT NULL,
            status              VARCHAR NOT NULL DEFAULT 'ACTIVE',
            appointment_id      UUID REFERENCES appointments(id),
            expires_at          TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(sa.text("""
        ALTER TABLE reservations ADD CONSTRAINT no_overlap_active
            EXCLUDE USING gist (
                company_id WITH =,
                professional_id WITH =,
                tstzrange(start_at, end_at, '[)') WITH &&
            ) WHERE (status = 'ACTIVE')
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON reservations
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE reservations ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS reservations CASCADE"))
