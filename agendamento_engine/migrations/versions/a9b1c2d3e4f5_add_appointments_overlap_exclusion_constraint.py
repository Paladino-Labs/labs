"""add_appointments_overlap_exclusion_constraint

Adiciona EXCLUDE CONSTRAINT para evitar sobreposição de agendamentos
por profissional dentro do mesmo tenant.

Statuses que ativam a constraint (bloqueiam o slot):
  CONFIRMED, PENDING, COMPLETED, NO_SHOW

Statuses que NÃO ativam (slot fica livre):
  CANCELLED, FAILED, EXPIRED

NO_SHOW e COMPLETED ativam intencionalmente — slot historicamente
ocupado; excluí-los permitiria backdating administrativo no mesmo slot.

Revision ID: a9b1c2d3e4f5
Revises: f1e2d3c4b5a6
Create Date: 2026-05-26

"""
from typing import Sequence, Union

from alembic import op

revision: str = "a9b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f1e2d3c4b5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensão necessária para usar GIST com tipos escalares (UUID, tsrange).
    # IF NOT EXISTS: idempotente; seguro se já ativa no Supabase.
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.execute(
        """
        ALTER TABLE appointments
          ADD CONSTRAINT no_overlap_per_professional
          EXCLUDE USING gist (
            company_id      WITH =,
            professional_id WITH =,
            tstzrange(start_at, end_at, '[)') WITH &&
          )
          WHERE (status NOT IN ('CANCELLED', 'FAILED', 'EXPIRED'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE appointments DROP CONSTRAINT IF EXISTS no_overlap_per_professional"
    )
