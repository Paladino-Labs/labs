"""packages

Revision ID: h3i4j5k6l7m8
Revises: g4h5i6j7k8l9
Create Date: 2026-06-08

Sprint 14 — Pacotes:
  1. Nova tabela packages (com RLS)
  2. Nova tabela package_purchases (com RLS)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "h3i4j5k6l7m8"
down_revision: Union[str, Sequence[str], None] = "g4h5i6j7k8l9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS packages (
            package_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            name              VARCHAR NOT NULL,
            service_id        UUID REFERENCES services(id),
            total_cotas       INTEGER NOT NULL CHECK (total_cotas > 0),
            price             NUMERIC(10,2) NOT NULL CHECK (price >= 0),
            validity_days     INTEGER,
            is_active         BOOLEAN NOT NULL DEFAULT true,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON packages
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE packages ENABLE ROW LEVEL SECURITY"))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS package_purchases (
            purchase_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id        UUID NOT NULL REFERENCES companies(id),
            customer_id       UUID NOT NULL REFERENCES customers(id),
            package_id        UUID NOT NULL REFERENCES packages(package_id),
            seller_user_id    UUID REFERENCES users(id),
            payment_id        UUID REFERENCES payments(payment_id),
            total_price       NUMERIC(10,2) NOT NULL,
            status            VARCHAR NOT NULL DEFAULT 'PENDING_PAYMENT',
            activated_at      TIMESTAMPTZ,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON package_purchases
            USING (company_id = current_setting('app.company_id', TRUE)::UUID)
    """))
    op.execute(sa.text("ALTER TABLE package_purchases ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS package_purchases"))
    op.execute(sa.text("DROP TABLE IF EXISTS packages"))
