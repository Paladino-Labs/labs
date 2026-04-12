"""sprint2_whatsapp

Revision ID: b7c3d1e9f2a5
Revises: f3a9e1d72b04
Create Date: 2026-04-12

Prepara o banco para a Fase 6 (Bot WhatsApp + Evolution API).

Mudanças:
  a. Refina bot_sessions: renomeia phone→whatsapp_id, adiciona last_message_id e
     expires_at, troca índice por UNIQUE constraint, corrige default de state.
  b. Cria whatsapp_connections (1 por empresa).
  c. Adiciona bot_enabled em company_settings (default False).
  d. Adiciona índice (company_id, phone) em customers para lookup rápido por número.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b7c3d1e9f2a5'
down_revision: Union[str, Sequence[str], None] = 'd8e3c2b51f70'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # =========================================================================
    # a. Refinar bot_sessions
    # =========================================================================

    # Remover índice antigo não-único
    op.drop_index('ix_bot_sessions_company_phone', table_name='bot_sessions')

    # Renomear coluna phone → whatsapp_id e ampliar para VARCHAR(30)
    op.alter_column(
        'bot_sessions', 'phone',
        new_column_name='whatsapp_id',
        existing_type=sa.String(20),
        type_=sa.String(30),
        nullable=False,
    )

    # Corrigir default de state de 'GREETING' para 'INICIO'
    op.alter_column(
        'bot_sessions', 'state',
        existing_type=sa.String(50),
        server_default='INICIO',
    )

    # Adicionar last_message_id para idempotência de webhook
    op.add_column(
        'bot_sessions',
        sa.Column('last_message_id', sa.String(100), nullable=True),
    )

    # Adicionar expires_at para TTL da sessão
    op.add_column(
        'bot_sessions',
        sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # Criar UNIQUE constraint (company_id, whatsapp_id)
    op.create_unique_constraint(
        'uq_bot_sessions_company_whatsapp',
        'bot_sessions',
        ['company_id', 'whatsapp_id'],
    )

    # =========================================================================
    # b. Criar whatsapp_connections
    # =========================================================================
    op.create_table(
        'whatsapp_connections',
        sa.Column('id', postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('company_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('companies.id'), nullable=False, unique=True),
        sa.Column('instance_name', sa.String(100), nullable=False, unique=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='DISCONNECTED'),
        sa.Column('phone_number', sa.String(30), nullable=True),
        sa.Column('qr_code', sa.Text, nullable=True),
        sa.Column('qr_generated_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('connected_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('disconnect_reason', sa.String(200), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )

    # =========================================================================
    # c. Adicionar bot_enabled em company_settings
    # =========================================================================
    op.add_column(
        'company_settings',
        sa.Column('bot_enabled', sa.Boolean(), nullable=False, server_default='false'),
    )

    # =========================================================================
    # d. Índice composto (company_id, phone) em customers para lookup por WhatsApp
    # =========================================================================
    op.create_index(
        'ix_customers_company_phone',
        'customers',
        ['company_id', 'phone'],
    )


def downgrade() -> None:
    # d. Remover índice de customers
    op.drop_index('ix_customers_company_phone', table_name='customers')

    # c. Remover bot_enabled
    op.drop_column('company_settings', 'bot_enabled')

    # b. DROP whatsapp_connections
    op.drop_table('whatsapp_connections')

    # a. Reverter bot_sessions
    op.drop_constraint('uq_bot_sessions_company_whatsapp', 'bot_sessions', type_='unique')
    op.drop_column('bot_sessions', 'expires_at')
    op.drop_column('bot_sessions', 'last_message_id')
    op.alter_column(
        'bot_sessions', 'whatsapp_id',
        new_column_name='phone',
        existing_type=sa.String(30),
        type_=sa.String(20),
        nullable=False,
    )
    op.alter_column(
        'bot_sessions', 'state',
        existing_type=sa.String(50),
        server_default='GREETING',
    )
    op.create_index('ix_bot_sessions_company_phone', 'bot_sessions', ['company_id', 'phone'])
