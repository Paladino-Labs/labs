"""align_remaining_tables

Revision ID: d8e3c2b51f70
Revises: c7b2f4e91a30
Create Date: 2026-04-11

Adiciona colunas faltantes nas tabelas que ficaram de fora da migration
de alinhamento anterior:

  companies           → slug, active, created_at, updated_at
  professionals       → created_at, updated_at
  services            → created_at, updated_at
  professional_services → company_id
  company_settings    → slot_interval_minutes, max_advance_booking_days,
                         require_payment_upfront (faltavam no banco)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd8e3c2b51f70'
down_revision: Union[str, Sequence[str], None] = 'c7b2f4e91a30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text('now()')


def upgrade() -> None:
    # ── companies ────────────────────────────────────────────────
    op.add_column('companies',
        sa.Column('slug', sa.String(100), nullable=True, unique=True))
    op.add_column('companies',
        sa.Column('active', sa.Boolean(), server_default='true', nullable=False))
    op.add_column('companies',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))
    op.add_column('companies',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))

    # ── professionals ─────────────────────────────────────────────
    op.add_column('professionals',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))
    op.add_column('professionals',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))

    # ── services ─────────────────────────────────────────────────
    op.add_column('services',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))
    op.add_column('services',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=_NOW, nullable=False))

    # ── professional_services — adiciona company_id ───────────────
    op.add_column('professional_services',
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=True))
    # Popula company_id a partir do profissional
    op.execute("""
        UPDATE professional_services ps
        SET company_id = p.company_id
        FROM professionals p
        WHERE ps.professional_id = p.id
    """)
    op.alter_column('professional_services', 'company_id', nullable=False)
    op.create_foreign_key(
        'fk_prof_services_company',
        'professional_services', 'companies',
        ['company_id'], ['id'],
    )
    op.create_index('ix_professional_services_company_id',
                    'professional_services', ['company_id'])

    # ── company_settings — colunas faltantes ─────────────────────
    op.add_column('company_settings',
        sa.Column('slot_interval_minutes', sa.Integer(),
                  server_default='15', nullable=False))
    op.add_column('company_settings',
        sa.Column('max_advance_booking_days', sa.Integer(),
                  server_default='60', nullable=False))
    op.add_column('company_settings',
        sa.Column('require_payment_upfront', sa.Boolean(),
                  server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('company_settings', 'require_payment_upfront')
    op.drop_column('company_settings', 'max_advance_booking_days')
    op.drop_column('company_settings', 'slot_interval_minutes')

    op.drop_index('ix_professional_services_company_id',
                  table_name='professional_services')
    op.drop_constraint('fk_prof_services_company',
                       'professional_services', type_='foreignkey')
    op.drop_column('professional_services', 'company_id')

    op.drop_column('services', 'updated_at')
    op.drop_column('services', 'created_at')
    op.drop_column('professionals', 'updated_at')
    op.drop_column('professionals', 'created_at')
    op.drop_column('companies', 'updated_at')
    op.drop_column('companies', 'created_at')
    op.drop_column('companies', 'active')
    op.drop_column('companies', 'slug')
