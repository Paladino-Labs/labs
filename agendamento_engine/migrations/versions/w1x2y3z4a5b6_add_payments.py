"""add_payments

Revision ID: w1x2y3z4a5b6
Revises: v1w2x3y4z5a6
Create Date: 2026-05-30

Cria tabela payments com FSM de status e trigger de imutabilidade de provider.
payment_method registra o método usado (CASH/PIX/BOLETO/CARD_CREDIT/CARD_DEBIT/MAQUININHA).
payment_source_id é nullable — preenchido apenas para cartão salvo.
RLS tenant_isolation por company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "w1x2y3z4a5b6"
down_revision: Union[str, Sequence[str], None] = "v1w2x3y4z5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id              UUID NOT NULL REFERENCES companies(id),
            customer_id             UUID REFERENCES customers(id),
            appointment_id          UUID REFERENCES appointments(id),
            currency                CHAR(3) NOT NULL DEFAULT 'BRL',

            gross_catalog_amount    NUMERIC(15,2) NOT NULL,
            discount_amount         NUMERIC(15,2) NOT NULL DEFAULT 0,
            net_charged_amount      NUMERIC(15,2) NOT NULL,
            provider_fee            NUMERIC(15,2) NOT NULL DEFAULT 0,

            payment_method          VARCHAR NOT NULL,
            payment_source_id       UUID REFERENCES payment_sources(source_id),

            provider                VARCHAR NOT NULL,
            target_account_id       UUID NOT NULL REFERENCES accounts(account_id),
            external_charge_id      VARCHAR,

            status                  VARCHAR NOT NULL DEFAULT 'PENDING',
            manual_override_count   INTEGER NOT NULL DEFAULT 0,

            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            paid_at                 TIMESTAMPTZ,
            refunded_at             TIMESTAMPTZ
        )
    """))

    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_payment_provider_change()
        RETURNS trigger AS $$
        BEGIN
            IF OLD.provider IS DISTINCT FROM NEW.provider THEN
                RAISE EXCEPTION 'Payment.provider e imutavel apos criacao';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """))

    op.execute(sa.text("""
        CREATE TRIGGER payment_provider_immutable
            BEFORE UPDATE OF provider ON payments FOR EACH ROW
            EXECUTE FUNCTION prevent_payment_provider_change()
    """))

    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON payments
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))

    op.execute(sa.text("ALTER TABLE payments ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS payments CASCADE"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prevent_payment_provider_change() CASCADE"))
