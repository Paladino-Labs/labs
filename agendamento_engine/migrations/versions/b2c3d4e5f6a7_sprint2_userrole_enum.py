"""sprint2_userrole_enum

Cria o tipo enum 'userrole' no PostgreSQL com 9 valores e altera
users.role de String(20) para userrole.

Valores ativos no Estágio 0:
  OWNER, ADMIN, OPERATOR, PROFESSIONAL, CLIENT, PLATFORM_OWNER

[SCHEMA APENAS] — Estágio 1+:
  PLATFORM_SUPPORT, PLATFORM_BILLING, PLATFORM_READONLY

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Pré-validação obrigatória antes de rodar em produção:
#   SELECT DISTINCT role FROM users;
# Deve retornar apenas ADMIN, PROFESSIONAL, CLIENT.
# Qualquer valor fora desse conjunto causará falha no USING role::userrole.


def upgrade() -> None:
    # 1. Criar enum
    userrole = sa.Enum(
        "OWNER",
        "ADMIN",
        "OPERATOR",
        "PROFESSIONAL",
        "CLIENT",
        "PLATFORM_OWNER",
        "PLATFORM_SUPPORT",
        "PLATFORM_BILLING",
        "PLATFORM_READONLY",
        name="userrole",
    )
    userrole.create(op.get_bind(), checkfirst=True)

    # 2. Remover default antigo
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role DROP DEFAULT
    """)

    # 3. (Opcional, mas recomendado)
    # Normalizar valores antigos antes do cast
    # Ajuste conforme seus dados reais
    op.execute("""
        UPDATE users
        SET role = UPPER(role)
    """)

    # 4. Converter coluna para enum
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role TYPE userrole
        USING role::userrole
    """)

    # 5. Recriar default usando enum
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role SET DEFAULT 'ADMIN'::userrole
    """)


def downgrade() -> None:
    # 1. Remover default enum
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role DROP DEFAULT
    """)

    # 2. Converter de volta para VARCHAR
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role TYPE VARCHAR(20)
        USING role::text
    """)

    # 3. Restaurar default string
    op.execute("""
        ALTER TABLE users
        ALTER COLUMN role SET DEFAULT 'ADMIN'
    """)

    # 4. Remover enum
    sa.Enum(name="userrole").drop(op.get_bind(), checkfirst=True)
