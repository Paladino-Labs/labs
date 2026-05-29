"""criando_tabela_blindadas

Revision ID: 16014789aa88
Revises: 
Create Date: 2026-02-18 06:55:24.224583

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '16014789aa88'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    """Verifica se uma coluna existe na tabela antes de tentar removê-la."""
    from sqlalchemy import inspect, text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :t AND column_name = :c AND table_schema = 'public'"
    ), {"t": table, "c": column})
    return result.fetchone() is not None


def _constraint_exists(constraint: str, table: str) -> bool:
    """Verifica se um constraint existe antes de tentar removê-lo."""
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM information_schema.table_constraints "
        "WHERE constraint_name = :n AND table_name = :t AND table_schema = 'public'"
    ), {"n": constraint, "t": table})
    return result.fetchone() is not None


def _index_exists(index: str) -> bool:
    """Verifica se um index existe antes de tentar removê-lo."""
    from sqlalchemy import text
    conn = op.get_bind()
    result = conn.execute(text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :n AND schemaname = 'public'"
    ), {"n": index})
    return result.fetchone() is not None


def upgrade() -> None:
    """Upgrade schema — idempotente: tolera bancos já migrados ou criados do zero."""
    # appointment_services: normalizar tipos (TEXT→String, INTEGER→Numeric)
    # Só altera se a coluna existe com o tipo antigo; caso contrário já está correto.
    conn = op.get_bind()
    from sqlalchemy import text

    # Verificar tipo atual de service_name antes de alterar
    r = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='appointment_services' AND column_name='service_name' AND table_schema='public'"
    )).fetchone()
    if r and r[0].lower() == 'text':
        op.alter_column('appointment_services', 'service_name',
                   existing_type=sa.TEXT(), type_=sa.String(), existing_nullable=False)

    r = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='appointment_services' AND column_name='duration_snapshot' AND table_schema='public'"
    )).fetchone()
    if r and r[0].lower() == 'integer':
        op.alter_column('appointment_services', 'duration_snapshot',
                   existing_type=sa.INTEGER(), type_=sa.Numeric(), existing_nullable=False)

    # Drops condicionais: colunas que existiam no schema antigo mas não no atual
    if _column_exists('appointment_services', 'created_at'):
        op.drop_column('appointment_services', 'created_at')

    # appointment_status_log: adicionar colunas novas (idempotente via IF NOT EXISTS)
    op.execute(text(
        "ALTER TABLE appointment_status_log "
        "ADD COLUMN IF NOT EXISTS from_status VARCHAR"
    ))
    op.execute(text(
        "ALTER TABLE appointment_status_log "
        "ADD COLUMN IF NOT EXISTS to_status VARCHAR"
    ))
    if _constraint_exists('appointment_status_log_appointment_id_fkey', 'appointment_status_log'):
        op.drop_constraint(
            op.f('appointment_status_log_appointment_id_fkey'),
            'appointment_status_log', type_='foreignkey'
        )
    # Recriar FK sem nome (idempotente: cria apenas se não existir)
    if not _constraint_exists('appointment_status_log_appointment_id_fkey', 'appointment_status_log'):
        op.create_foreign_key(None, 'appointment_status_log', 'appointments', ['appointment_id'], ['id'])
    if _column_exists('appointment_status_log', 'status'):
        op.drop_column('appointment_status_log', 'status')

    # appointments: adicionar colunas novas
    op.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS company_id UUID"))
    op.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS version INTEGER"))
    op.execute(text("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS status VARCHAR"))

    r = conn.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name='appointments' AND column_name='idempotency_key' AND table_schema='public'"
    )).fetchone()
    if r and r[0].lower() == 'text':
        op.alter_column('appointments', 'idempotency_key',
                   existing_type=sa.TEXT(), type_=sa.String(), existing_nullable=False)

    if _constraint_exists('unique_idempotency', 'appointments'):
        op.drop_constraint(op.f('unique_idempotency'), 'appointments', type_='unique')

    if not _index_exists('ix_appointments_company_id'):
        op.create_index(op.f('ix_appointments_company_id'), 'appointments', ['company_id'], unique=False)
    if not _index_exists('ix_appointments_professional_id'):
        op.create_index(op.f('ix_appointments_professional_id'), 'appointments', ['professional_id'], unique=False)
    if not _constraint_exists('uq_idempotency', 'appointments'):
        op.create_unique_constraint('uq_idempotency', 'appointments', ['company_id', 'idempotency_key'])

    if _column_exists('appointments', 'tenant_id'):
        op.drop_column('appointments', 'tenant_id')
    if _column_exists('appointments', 'created_at'):
        op.drop_column('appointments', 'created_at')

    # blocked_slots indexes
    if not _index_exists('ix_blocked_slots_company_id'):
        op.create_index(op.f('ix_blocked_slots_company_id'), 'blocked_slots', ['company_id'], unique=False)
    if not _index_exists('ix_blocked_slots_professional_id'):
        op.create_index(op.f('ix_blocked_slots_professional_id'), 'blocked_slots', ['professional_id'], unique=False)

    # working_hours
    if _index_exists('idx_working_hours_active'):
        op.drop_index(op.f('idx_working_hours_active'), table_name='working_hours',
                      postgresql_where='(is_active = true)')
    if _constraint_exists('working_hours_company_id_professional_id_weekday_key', 'working_hours'):
        op.drop_constraint(
            op.f('working_hours_company_id_professional_id_weekday_key'),
            'working_hours', type_='unique'
        )
    if not _index_exists('ix_working_hours_company_id'):
        op.create_index(op.f('ix_working_hours_company_id'), 'working_hours', ['company_id'], unique=False)
    if not _index_exists('ix_working_hours_professional_id'):
        op.create_index(op.f('ix_working_hours_professional_id'), 'working_hours', ['professional_id'], unique=False)
    if not _constraint_exists('uq_working_hours_day', 'working_hours'):
        op.create_unique_constraint('uq_working_hours_day', 'working_hours',
                                    ['company_id', 'professional_id', 'weekday'])


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('uq_working_hours_day', 'working_hours', type_='unique')
    op.drop_index(op.f('ix_working_hours_professional_id'), table_name='working_hours')
    op.drop_index(op.f('ix_working_hours_company_id'), table_name='working_hours')
    op.create_unique_constraint(op.f('working_hours_company_id_professional_id_weekday_key'), 'working_hours', ['company_id', 'professional_id', 'weekday'], postgresql_nulls_not_distinct=False)
    op.create_index(op.f('idx_working_hours_active'), 'working_hours', ['company_id', 'professional_id'], unique=False, postgresql_where='(is_active = true)')
    op.drop_index(op.f('ix_blocked_slots_professional_id'), table_name='blocked_slots')
    op.drop_index(op.f('ix_blocked_slots_company_id'), table_name='blocked_slots')
    op.add_column('appointments', sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False))
    op.add_column('appointments', sa.Column('tenant_id', sa.UUID(), autoincrement=False, nullable=False))
    op.drop_constraint('uq_idempotency', 'appointments', type_='unique')
    op.drop_index(op.f('ix_appointments_professional_id'), table_name='appointments')
    op.drop_index(op.f('ix_appointments_company_id'), table_name='appointments')
    op.create_unique_constraint(op.f('unique_idempotency'), 'appointments', ['tenant_id', 'idempotency_key'], postgresql_nulls_not_distinct=False)
    op.alter_column('appointments', 'idempotency_key',
               existing_type=sa.String(),
               type_=sa.TEXT(),
               existing_nullable=False)
    op.drop_column('appointments', 'status')
    op.drop_column('appointments', 'version')
    op.drop_column('appointments', 'company_id')
    op.add_column('appointment_status_log', sa.Column('status', sa.TEXT(), autoincrement=False, nullable=False))
    op.drop_constraint(None, 'appointment_status_log', type_='foreignkey')
    op.create_foreign_key(op.f('appointment_status_log_appointment_id_fkey'), 'appointment_status_log', 'appointments', ['appointment_id'], ['id'], ondelete='CASCADE')
    op.drop_column('appointment_status_log', 'to_status')
    op.drop_column('appointment_status_log', 'from_status')
    op.add_column('appointment_services', sa.Column('created_at', postgresql.TIMESTAMP(timezone=True), server_default=sa.text('now()'), autoincrement=False, nullable=False))
    op.alter_column('appointment_services', 'duration_snapshot',
               existing_type=sa.Numeric(),
               type_=sa.INTEGER(),
               existing_nullable=False)
    op.alter_column('appointment_services', 'service_name',
               existing_type=sa.String(),
               type_=sa.TEXT(),
               existing_nullable=False)
    # ### end Alembic commands ###
