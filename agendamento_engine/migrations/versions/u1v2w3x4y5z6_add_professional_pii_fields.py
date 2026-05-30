"""add_professional_pii_fields

Revision ID: u1v2w3x4y5z6
Revises: t1u2v3w4x5y6
Create Date: 2026-05-30

Adiciona campos PII criptografados em professionals:
  cpf_cnpj_encrypted (Fernet), cpf_cnpj_hash (HMAC-SHA256),
  cpf_cnpj_masked, external_wallet_id.

Unicidade por hash para deduplicação sem plaintext.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "t1u2v3w4x5y6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_encrypted TEXT"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_hash TEXT"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals ADD COLUMN IF NOT EXISTS cpf_cnpj_masked VARCHAR(18)"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals ADD COLUMN IF NOT EXISTS external_wallet_id VARCHAR"
    ))
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_professional_cpf_cnpj_hash
            ON professionals(company_id, cpf_cnpj_hash)
            WHERE cpf_cnpj_hash IS NOT NULL
    """))


def downgrade() -> None:
    op.execute(sa.text(
        "DROP INDEX IF EXISTS uq_professional_cpf_cnpj_hash"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals DROP COLUMN IF EXISTS external_wallet_id"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals DROP COLUMN IF EXISTS cpf_cnpj_masked"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals DROP COLUMN IF EXISTS cpf_cnpj_hash"
    ))
    op.execute(sa.text(
        "ALTER TABLE professionals DROP COLUMN IF EXISTS cpf_cnpj_encrypted"
    ))
