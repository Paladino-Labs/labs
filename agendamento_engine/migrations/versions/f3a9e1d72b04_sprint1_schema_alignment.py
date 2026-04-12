"""sprint1_schema_alignment

Revision ID: f3a9e1d72b04
Revises: a8c81686f38e
Create Date: 2026-04-11

Alinha o schema do banco (criado com modelos legados) com os modelos canônicos
da nova arquitetura (app.infrastructure.db.models).

Mudanças:
  a. Migrar status: 'pending'/'confirmed' → 'SCHEDULED' (e demais)
  b. Migrar financial_status: 'pending' → 'UNPAID' (e demais)
  c. DROP + recreate CHECK constraint de status com novos valores
  d. Colunas faltantes em appointments: cancel_reason, created_at, updated_at
  d+. Colunas faltantes em appointment_status_log: company_id, changed_by, note
  e. Colunas faltantes em clients: active, created_at, updated_at
  f. Rename clients → customers
  g. Rename blocked_slots → schedule_blocks + created_at, updated_at
  h. CREATE TABLE availability_slots
  i. CREATE TABLE bot_sessions
  j. Recriar EXCLUDE CONSTRAINT com WHERE (status NOT IN ('CANCELLED','NO_SHOW'))
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'f3a9e1d72b04'
down_revision: Union[str, Sequence[str], None] = 'a8c81686f38e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # c. DROP CHECK constraint de status PRIMEIRO (libera o UPDATE abaixo)
    # =========================================================================
    op.drop_constraint('appointments_status_check', 'appointments', type_='check')

    # =========================================================================
    # a. Migrar valores de status: legado → novo modelo
    # =========================================================================
    op.execute("UPDATE appointments SET status = 'SCHEDULED'  WHERE status IN ('pending', 'confirmed')")
    op.execute("UPDATE appointments SET status = 'COMPLETED'  WHERE status = 'completed'")
    op.execute("UPDATE appointments SET status = 'CANCELLED'  WHERE status = 'cancelled'")
    op.execute("UPDATE appointments SET status = 'NO_SHOW'    WHERE status = 'no_show'")

    # =========================================================================
    # b. Migrar valores de financial_status: legado → novo modelo
    # =========================================================================
    op.execute("UPDATE appointments SET financial_status = 'UNPAID'   WHERE financial_status IN ('pending', 'cancelled')")
    op.execute("UPDATE appointments SET financial_status = 'PAID'     WHERE financial_status = 'paid'")
    op.execute("UPDATE appointments SET financial_status = 'REFUNDED' WHERE financial_status = 'refunded'")
    op.execute("ALTER TABLE appointments ALTER COLUMN financial_status SET DEFAULT 'UNPAID'")

    # Recria CHECK constraint com os novos valores
    op.create_check_constraint(
        'appointments_status_check',
        'appointments',
        "status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'NO_SHOW')",
    )

    # =========================================================================
    # d. Colunas faltantes em appointments
    # =========================================================================
    op.add_column('appointments',
        sa.Column('cancel_reason', sa.String(500), nullable=True))
    op.add_column('appointments',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))
    op.add_column('appointments',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))

    # =========================================================================
    # d+. Colunas faltantes em appointment_status_log
    #     (necessário para transitions.py: company_id, changed_by, note)
    # =========================================================================
    # company_id: adiciona nullable, popula de appointments, torna NOT NULL
    op.add_column('appointment_status_log',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("""
        UPDATE appointment_status_log asl
        SET company_id = a.company_id
        FROM appointments a
        WHERE asl.appointment_id = a.id
    """)
    op.alter_column('appointment_status_log', 'company_id', nullable=False)
    op.create_foreign_key(
        'fk_status_log_company',
        'appointment_status_log', 'companies',
        ['company_id'], ['id'],
    )

    # changed_by: nullable (quem triggou a transição)
    op.add_column('appointment_status_log',
        sa.Column('changed_by', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_status_log_changed_by',
        'appointment_status_log', 'users',
        ['changed_by'], ['id'],
    )

    # note: texto livre opcional
    op.add_column('appointment_status_log',
        sa.Column('note', sa.String(500), nullable=True))

    # =========================================================================
    # e. Colunas faltantes em clients
    # =========================================================================
    op.add_column('clients',
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('clients',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))
    op.add_column('clients',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))

    # =========================================================================
    # f. Rename clients → customers
    # =========================================================================
    op.rename_table('clients', 'customers')

    # =========================================================================
    # g. Rename blocked_slots → schedule_blocks + TimestampMixin columns
    # =========================================================================
    op.rename_table('blocked_slots', 'schedule_blocks')
    op.add_column('schedule_blocks',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))
    op.add_column('schedule_blocks',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))

    # =========================================================================
    # h. CREATE TABLE availability_slots
    # =========================================================================
    op.create_table(
        'availability_slots',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('professional_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('professionals.id'), nullable=False),
        sa.Column('service_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('services.id'), nullable=True),
        sa.Column('start_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('end_at',   sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('status',   sa.String(20), nullable=False, server_default='AVAILABLE'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint(
            'company_id', 'professional_id', 'start_at',
            name='uq_availability_slot',
        ),
    )
    op.create_index('ix_availability_slots_company_id', 'availability_slots', ['company_id'])

    # =========================================================================
    # i. CREATE TABLE bot_sessions
    # =========================================================================
    op.create_table(
        'bot_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('phone', sa.String(20), nullable=False),
        sa.Column('state', sa.String(50), nullable=False, server_default='GREETING'),
        sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_message_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_bot_sessions_company_phone', 'bot_sessions', ['company_id', 'phone'])

    # =========================================================================
    # j. Recriar EXCLUDE CONSTRAINT com WHERE filtrando cancelados/no-shows
    #    (op.drop_constraint não suporta type_='exclude' — usar SQL raw)
    # =========================================================================
    op.execute("ALTER TABLE appointments DROP CONSTRAINT no_overlapping_appointments")
    op.execute("""
        ALTER TABLE appointments
        ADD CONSTRAINT no_overlapping_appointments
        EXCLUDE USING GIST (
            professional_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        )
        WHERE (status NOT IN ('CANCELLED', 'NO_SHOW'))
    """)


def downgrade() -> None:
    # j. Reverter EXCLUDE CONSTRAINT (sem WHERE)
    op.execute("ALTER TABLE appointments DROP CONSTRAINT no_overlapping_appointments")
    op.execute("""
        ALTER TABLE appointments
        ADD CONSTRAINT no_overlapping_appointments
        EXCLUDE USING GIST (
            professional_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        )
    """)

    # i. DROP bot_sessions
    op.drop_index('ix_bot_sessions_company_phone', table_name='bot_sessions')
    op.drop_table('bot_sessions')

    # h. DROP availability_slots
    op.drop_index('ix_availability_slots_company_id', table_name='availability_slots')
    op.drop_table('availability_slots')

    # g. Reverter schedule_blocks → blocked_slots
    op.drop_column('schedule_blocks', 'updated_at')
    op.drop_column('schedule_blocks', 'created_at')
    op.rename_table('schedule_blocks', 'blocked_slots')

    # f. Reverter customers → clients
    op.rename_table('customers', 'clients')

    # e. Remover colunas de clients
    op.drop_column('clients', 'updated_at')
    op.drop_column('clients', 'created_at')
    op.drop_column('clients', 'active')

    # d+. Reverter appointment_status_log
    op.drop_column('appointment_status_log', 'note')
    op.drop_constraint('fk_status_log_changed_by', 'appointment_status_log', type_='foreignkey')
    op.drop_column('appointment_status_log', 'changed_by')
    op.drop_constraint('fk_status_log_company', 'appointment_status_log', type_='foreignkey')
    op.drop_column('appointment_status_log', 'company_id')

    # d. Remover colunas de appointments
    op.drop_column('appointments', 'updated_at')
    op.drop_column('appointments', 'created_at')
    op.drop_column('appointments', 'cancel_reason')

    # c. Reverter CHECK constraint de status
    op.drop_constraint('appointments_status_check', 'appointments', type_='check')
    op.create_check_constraint(
        'appointments_status_check',
        'appointments',
        "status = ANY (ARRAY['pending'::text, 'confirmed'::text, "
        "'cancelled'::text, 'completed'::text, 'no_show'::text])",
    )

    # b. Reverter financial_status
    op.execute("UPDATE appointments SET financial_status = 'pending'  WHERE financial_status IN ('UNPAID')")
    op.execute("UPDATE appointments SET financial_status = 'paid'     WHERE financial_status = 'PAID'")
    op.execute("UPDATE appointments SET financial_status = 'refunded' WHERE financial_status = 'REFUNDED'")
    op.execute("ALTER TABLE appointments ALTER COLUMN financial_status SET DEFAULT 'pending'")

    # a. Reverter status
    op.execute("UPDATE appointments SET status = 'pending'   WHERE status IN ('SCHEDULED', 'IN_PROGRESS')")
    op.execute("UPDATE appointments SET status = 'completed' WHERE status = 'COMPLETED'")
    op.execute("UPDATE appointments SET status = 'cancelled' WHERE status = 'CANCELLED'")
    op.execute("UPDATE appointments SET status = 'no_show'   WHERE status = 'NO_SHOW'")
