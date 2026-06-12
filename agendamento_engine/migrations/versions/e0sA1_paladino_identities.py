"""paladino_identities — identidade global Paladino-wide

Revision ID: e0sA1_paladino_identities
Revises: e0sB1_appointment_manage_tokens
Create Date: 2026-06-11

Sprint A — Identidade Paladino (1/3):
  Tabela GLOBAL (sem company_id) — quebra o padrão RLS do projeto
  INTENCIONALMENTE (Risco 1 do plano). RLS é HABILITADO sem nenhuma
  policy permissiva: queries tenant-scoped não enxergam nada; o acesso
  é exclusivamente via service layer (sessão superuser/role de serviço
  bypassa RLS no Supabase).

  CPF segue o padrão PII do Sprint 8: cpf_encrypted (Fernet) +
  cpf_hash (HMAC-SHA256) + cpf_masked. Nunca plaintext.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sA1_paladino_identities"
down_revision: Union[str, Sequence[str], None] = "e0sB1_appointment_manage_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS paladino_identities (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phone_e164                  VARCHAR(20) NOT NULL UNIQUE,
            phone_national_normalized   VARCHAR(20) NOT NULL,
            possible_aliases            JSONB NOT NULL DEFAULT '[]',
            name                        VARCHAR(255),
            email                       VARCHAR(255),
            cpf_encrypted               TEXT,
            cpf_hash                    VARCHAR(64),
            cpf_masked                  VARCHAR(14),
            created_at                  TIMESTAMPTZ DEFAULT now(),
            updated_at                  TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_paladino_identities_phone_national "
        "ON paladino_identities (phone_national_normalized)"
    ))

    # RLS habilitado SEM policy: tabela global, invisível a sessões
    # tenant-scoped. Acesso exclusivamente via service layer.
    op.execute(sa.text(
        "ALTER TABLE paladino_identities ENABLE ROW LEVEL SECURITY"
    ))
    # Nenhuma CREATE POLICY aqui — intencional.


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS paladino_identities"))
