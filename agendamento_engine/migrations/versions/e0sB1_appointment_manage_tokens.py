"""appointment manage tokens — link de gestão sem login

Revision ID: e0sB1_appointment_manage_tokens
Revises: e0sE1_external_statement_entries
Create Date: 2026-06-11

Sprint B — Link de gestão com token único:
  1. appointments.manage_token_hash — SHA-256 do token cru (UUID4 enviado
     no link do WhatsApp; o token cru NUNCA é armazenado)
  2. appointments.manage_token_expires_at — expiração (= start_at do
     agendamento; após o início o link deixa de funcionar)
  3. Índice ÚNICO parcial em manage_token_hash (NULL não conflita)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sB1_appointment_manage_tokens"
down_revision: Union[str, Sequence[str], None] = "e0sE1_external_statement_entries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE appointments "
        "ADD COLUMN IF NOT EXISTS manage_token_hash VARCHAR(64)"
    ))
    op.execute(sa.text(
        "ALTER TABLE appointments "
        "ADD COLUMN IF NOT EXISTS manage_token_expires_at TIMESTAMPTZ"
    ))
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_appointments_manage_token_hash "
        "ON appointments (manage_token_hash) "
        "WHERE manage_token_hash IS NOT NULL"
    ))


def downgrade() -> None:
    op.execute(sa.text(
        "DROP INDEX IF EXISTS uq_appointments_manage_token_hash"
    ))
    op.execute(sa.text(
        "ALTER TABLE appointments DROP COLUMN IF EXISTS manage_token_expires_at"
    ))
    op.execute(sa.text(
        "ALTER TABLE appointments DROP COLUMN IF EXISTS manage_token_hash"
    ))
