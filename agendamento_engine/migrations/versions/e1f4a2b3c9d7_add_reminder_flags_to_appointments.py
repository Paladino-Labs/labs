"""add_reminder_flags_to_appointments

Revision ID: e1f4a2b3c9d7
Revises: b7c3d1e9f2a5
Create Date: 2026-04-14

Adiciona colunas de controle de lembretes em appointments:
  - reminder_24h_sent: flag de idempotência para lembrete de 24h
  - reminder_2h_sent:  flag de idempotência para lembrete de 2h

As flags garantem que cada lembrete seja enviado no máximo uma vez,
mesmo que o worker execute múltiplas vezes na janela de tempo.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f4a2b3c9d7"
down_revision: Union[str, None] = "b7c3d1e9f2a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "appointments",
        sa.Column(
            "reminder_24h_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    op.add_column(
        "appointments",
        sa.Column(
            "reminder_2h_sent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
    )
    # Índice parcial para o worker de lembretes: apenas agendamentos não enviados
    op.create_index(
        "ix_appointments_reminder_24h",
        "appointments",
        ["start_at"],
        postgresql_where=sa.text("reminder_24h_sent = FALSE AND status = 'SCHEDULED'"),
    )
    op.create_index(
        "ix_appointments_reminder_2h",
        "appointments",
        ["start_at"],
        postgresql_where=sa.text("reminder_2h_sent = FALSE AND status = 'SCHEDULED'"),
    )


def downgrade() -> None:
    op.drop_index("ix_appointments_reminder_2h", table_name="appointments")
    op.drop_index("ix_appointments_reminder_24h", table_name="appointments")
    op.drop_column("appointments", "reminder_2h_sent")
    op.drop_column("appointments", "reminder_24h_sent")
