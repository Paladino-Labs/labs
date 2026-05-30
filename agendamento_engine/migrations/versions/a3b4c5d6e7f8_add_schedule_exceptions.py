"""add_schedule_exceptions

Revision ID: a3b4c5d6e7f8
Revises: z1a2b3c4d5e6
Create Date: 2026-05-30

Cria tabela schedule_exceptions.
SUBSTITUTIVE (substitui horário padrão) | ADDITIVE (adiciona horário extra).
start_time/end_time nullable (NULL = dia todo de folga, apenas SUBSTITUTIVE).
UNIQUE(professional_id, exception_date, type).
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "z1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS schedule_exceptions (
            exception_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id          UUID NOT NULL REFERENCES companies(id),
            professional_id     UUID NOT NULL REFERENCES professionals(id),
            exception_date      DATE NOT NULL,
            type                VARCHAR NOT NULL,
            start_time          TIME,
            end_time            TIME,
            reason              VARCHAR,
            UNIQUE(professional_id, exception_date, type)
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON schedule_exceptions
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE schedule_exceptions ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS schedule_exceptions CASCADE"))
