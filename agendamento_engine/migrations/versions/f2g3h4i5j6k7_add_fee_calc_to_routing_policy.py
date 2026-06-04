"""add_fee_calc_fields_to_tenant_fee_routing_policies

Revision ID: f2g3h4i5j6k7
Revises: psg1a2b3c4d5
Create Date: 2026-06-04

Adiciona fee_percentage, fee_flat e is_active à tabela
tenant_fee_routing_policies para suportar cálculo automático de
taxa em pagamentos manuais de maquininha (MDR por adquirente local).

Não recria a tabela — apenas ADD COLUMN com IF NOT EXISTS para idempotência.
Os 7 registros por tenant já existem; nenhum INSERT é necessário.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2g3h4i5j6k7"
down_revision: Union[str, Sequence[str], None] = "psg1a2b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE tenant_fee_routing_policies
            ADD COLUMN IF NOT EXISTS fee_percentage NUMERIC(7,4) NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS fee_flat       NUMERIC(10,2) NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS is_active      BOOLEAN NOT NULL DEFAULT TRUE
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE tenant_fee_routing_policies
            DROP COLUMN IF EXISTS fee_percentage,
            DROP COLUMN IF EXISTS fee_flat,
            DROP COLUMN IF EXISTS is_active
    """))
