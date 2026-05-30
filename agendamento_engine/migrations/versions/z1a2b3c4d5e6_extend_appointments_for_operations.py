"""extend_appointments_for_operations

Revision ID: z1a2b3c4d5e6
Revises: y1z2a3b4c5d6
Create Date: 2026-05-30

Adiciona DRAFT e FAILED ao enum appointmentstatus.
Adiciona operation_type em appointments (SERVICE_SCHEDULED | SERVICE_DIRECT | PRODUCT_SALE).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "y1z2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # Verifica se o tipo enum appointmentstatus existe no banco.
    # No banco de produção, appointments.status é VARCHAR(20) — o enum nunca
    # foi criado, então ALTER TYPE deve ser ignorado.
    type_exists = conn.execute(sa.text(
        "SELECT 1 FROM pg_type WHERE typname = 'appointmentstatus' AND typtype = 'e'"
    )).fetchone()

    if type_exists:
        op.execute(sa.text("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'DRAFT'"))
        op.execute(sa.text("ALTER TYPE appointmentstatus ADD VALUE IF NOT EXISTS 'FAILED'"))
    # Se não existe (status é VARCHAR), DRAFT/FAILED já funcionam como strings — nada a fazer.

    op.execute(sa.text("""
        ALTER TABLE appointments
            ADD COLUMN IF NOT EXISTS operation_type VARCHAR NOT NULL DEFAULT 'SERVICE_SCHEDULED'
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE appointments DROP COLUMN IF EXISTS operation_type"))
    # Não é possível remover valores de um enum no PostgreSQL sem recriar o tipo.
    # DRAFT e FAILED ficam no enum após downgrade — aceitável para rollback de emergência.
