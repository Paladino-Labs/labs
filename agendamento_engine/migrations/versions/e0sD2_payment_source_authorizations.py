"""payment_source_authorizations — autorização de método de pagamento por tenant

Revision ID: e0sD2_payment_source_authorizations
Revises: e0sD1_portal_auth
Create Date: 2026-06-12

Sprint D — Portal do Cliente (2/2):
  Token de pagamento (Asaas payment_source) vinculado à identity GLOBAL,
  autorizado por tenant com mode ALWAYS | ONCE. Tabela de identidade —
  sem RLS tenant (RLS habilitado SEM policy, padrão e0sA1); acesso
  exclusivamente via service layer.

  Não confundir com a tabela legada payment_sources (tenant-scoped,
  customer_id) — esta é a autorização Paladino-wide do Portal.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sD2_payment_source_authorizations"
down_revision: Union[str, Sequence[str], None] = "e0sD1_portal_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payment_source_authorizations (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            identity_id   UUID NOT NULL
                          REFERENCES paladino_identities(id) ON DELETE CASCADE,
            company_id    UUID NOT NULL REFERENCES companies(id),
            source_token  VARCHAR(255) NOT NULL,
            provider      VARCHAR(20) NOT NULL DEFAULT 'ASAAS',
            mode          VARCHAR(10) NOT NULL,
            last_four     VARCHAR(4),
            brand         VARCHAR(20),
            granted_at    TIMESTAMPTZ DEFAULT now(),
            revoked_at    TIMESTAMPTZ,
            UNIQUE (identity_id, company_id, source_token)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_psa_identity "
        "ON payment_source_authorizations (identity_id)"
    ))

    # RLS habilitado SEM policy — tabela global, acesso só via service layer.
    op.execute(sa.text(
        "ALTER TABLE payment_source_authorizations ENABLE ROW LEVEL SECURITY"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS payment_source_authorizations"))
