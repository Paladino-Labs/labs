"""align_users_table

Revision ID: c7b2f4e91a30
Revises: f3a9e1d72b04
Create Date: 2026-04-11

Alinha a tabela users com o modelo canônico User:
  - Adiciona coluna role (VARCHAR) derivada de is_admin
  - Adiciona coluna active (BOOLEAN, default true)
  - Mantém is_admin por compatibilidade (pode ser removido futuramente)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c7b2f4e91a30'
down_revision: Union[str, Sequence[str], None] = 'f3a9e1d72b04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Adiciona role como nullable para popular antes de tornar NOT NULL
    op.add_column('users',
        sa.Column('role', sa.String(20), nullable=True))

    # Deriva role de is_admin
    op.execute("UPDATE users SET role = 'ADMIN'        WHERE is_admin = true")
    op.execute("UPDATE users SET role = 'PROFESSIONAL' WHERE is_admin = false")

    # Torna NOT NULL com default ADMIN
    op.alter_column('users', 'role', nullable=False,
                    server_default='ADMIN')

    # Adiciona active (todos os usuários existentes estão ativos)
    op.add_column('users',
        sa.Column('active', sa.Boolean(),
                  server_default='true', nullable=False))

    # TimestampMixin: created_at e updated_at (ausentes no schema legado)
    op.add_column('users',
        sa.Column('created_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))
    op.add_column('users',
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()'), nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'updated_at')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'active')
    op.drop_column('users', 'role')
