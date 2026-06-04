"""add_pagseguro_credential_provider

Revision ID: psg1a2b3c4d5
Revises: z1a2b3c4d5e6
Create Date: 2026-06-03

Adiciona 'PAGSEGURO' ao enum credentialprovider no PostgreSQL.

O valor é adicionado com IF NOT EXISTS para idempotência.
Downgrade: ALTER TYPE ... DROP VALUE não existe no PostgreSQL.
A migration de downgrade é intencional no-op — remover um valor
de enum exigiria recriar o tipo e todas as colunas que o usam,
o que implica indisponibilidade e risco de perda de dados.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "psg1a2b3c4d5"
down_revision: Union[str, Sequence[str], None] = "z1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TYPE credentialprovider ADD VALUE IF NOT EXISTS 'PAGSEGURO'"
    ))


def downgrade() -> None:
    # PostgreSQL não suporta DROP VALUE em enums.
    # Para reverter: recriar o tipo manualmente e migrar os dados.
    pass
