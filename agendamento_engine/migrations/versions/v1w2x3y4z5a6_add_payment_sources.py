"""add_payment_sources

Revision ID: v1w2x3y4z5a6
Revises: u1v2w3x4y5z6
Create Date: 2026-05-30

Cria tabela payment_sources — apenas métodos salvos/tokenizados (CARD_CREDIT | CARD_DEBIT).
PIX/BOLETO/CASH não são PaymentSources; usam payment_method no pagamento.
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "v1w2x3y4z5a6"
down_revision: Union[str, Sequence[str], None] = "u1v2w3x4y5z6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payment_sources (
            source_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id),
            customer_id     UUID NOT NULL REFERENCES customers(id),
            type            VARCHAR NOT NULL,
            provider        VARCHAR NOT NULL,
            external_token  TEXT NOT NULL,
            last4           VARCHAR(4),
            brand           VARCHAR,
            is_active       BOOLEAN NOT NULL DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON payment_sources
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE payment_sources ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS payment_sources CASCADE"))
