"""portal_credentials + portal_magic_tokens — auth do Portal do Cliente

Revision ID: e0sD1_portal_auth
Revises: e0sA3_customers_identity_link
Create Date: 2026-06-12

Sprint D — Portal do Cliente (1/2):
  Credenciais vinculadas à PaladinoIdentity (tabela GLOBAL, sem company_id).
  password_hash nullable: cliente pode autenticar só com magic link.
  portal_magic_tokens guarda APENAS o SHA-256 do token (cru nunca persiste —
  mesmo padrão do manage_token do Sprint B).

  RLS habilitado SEM policy (padrão e0sA1): tabelas globais invisíveis a
  sessões tenant-scoped; acesso exclusivamente via service layer.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sD1_portal_auth"
down_revision: Union[str, Sequence[str], None] = "e0sA3_customers_identity_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS portal_credentials (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            identity_id           UUID NOT NULL UNIQUE
                                  REFERENCES paladino_identities(id) ON DELETE CASCADE,
            email                 VARCHAR(255) NOT NULL UNIQUE,
            password_hash         VARCHAR(255),
            email_verified        BOOLEAN NOT NULL DEFAULT false,
            must_change_password  BOOLEAN NOT NULL DEFAULT false,
            last_login_at         TIMESTAMPTZ,
            created_at            TIMESTAMPTZ DEFAULT now(),
            updated_at            TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS portal_magic_tokens (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            identity_id  UUID NOT NULL
                         REFERENCES paladino_identities(id) ON DELETE CASCADE,
            token_hash   VARCHAR(64) NOT NULL UNIQUE,
            expires_at   TIMESTAMPTZ NOT NULL,
            used_at      TIMESTAMPTZ,
            created_at   TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_portal_magic_tokens_hash "
        "ON portal_magic_tokens (token_hash)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_portal_magic_tokens_identity "
        "ON portal_magic_tokens (identity_id)"
    ))

    # RLS habilitado SEM policy — tabelas globais, acesso só via service layer.
    op.execute(sa.text("ALTER TABLE portal_credentials ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("ALTER TABLE portal_magic_tokens ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS portal_magic_tokens"))
    op.execute(sa.text("DROP TABLE IF EXISTS portal_credentials"))
