"""promotions + coupons + redemptions + discount_applications

Revision ID: e0s16a_promotions_coupons
Revises: e0s17a_stock_suppliers_payables
Create Date: 2026-06-11

Sprint 16 — Promoções e Cupons (Decisão D1):
  1. promotions — PERCENTAGE/FIXED_AMOUNT/OVERRIDE_PRICE/FREE_ITEM,
     AUTOMATIC/COUPON_REQUIRED, cumulative, priority, conditions JSONB
  2. coupons — BULK/SINGLE_USE/PER_CUSTOMER, UNIQUE(company_id, code)
  3. coupon_redemptions — rastro de uso, reversível no refund
  4. discount_applications — rastro D1 por sequência; promotion_id NULLABLE
     (desconto manual usa promotion_id=NULL — divergência intencional do
     spec original, exigida pelo endpoint manual-discount)
  5. payments + coupon_code VARCHAR(50) nullable
     (manual_override_count já existe desde w1x2y3z4a5b6 — não recriado)
Todas as tabelas novas com RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s16a_promotions_coupons"
down_revision: Union[str, Sequence[str], None] = "e0s17a_stock_suppliers_payables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = [
    "promotions",
    "coupons",
    "coupon_redemptions",
    "discount_applications",
]


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text(f"""
        CREATE POLICY tenant_isolation ON {table}
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def upgrade() -> None:
    # 1. promotions
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS promotions (
            id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id             UUID NOT NULL REFERENCES companies(id),
            name                   VARCHAR(255) NOT NULL,
            description            TEXT,
            discount_type          VARCHAR(30) NOT NULL,
            discount_value         NUMERIC(15,2),
            application_mode       VARCHAR(20) NOT NULL DEFAULT 'AUTOMATIC',
            cumulative             BOOLEAN NOT NULL DEFAULT false,
            priority               INTEGER NOT NULL DEFAULT 0,
            status                 VARCHAR(20) NOT NULL DEFAULT 'DRAFT',
            valid_from             TIMESTAMPTZ,
            valid_until            TIMESTAMPTZ,
            max_uses               INTEGER,
            max_uses_per_customer  INTEGER,
            uses_count             INTEGER NOT NULL DEFAULT 0,
            conditions             JSONB,
            created_by             UUID NOT NULL REFERENCES users(id),
            created_at             TIMESTAMPTZ DEFAULT now(),
            updated_at             TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_promotions_company_id ON promotions (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_promotions_company_status "
        "ON promotions (company_id, status)"
    ))

    # 2. coupons
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS coupons (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            UUID NOT NULL REFERENCES companies(id),
            promotion_id          UUID NOT NULL REFERENCES promotions(id),
            code                  VARCHAR(50) NOT NULL,
            generation_type       VARCHAR(20) NOT NULL,
            max_uses              INTEGER,
            uses_count            INTEGER NOT NULL DEFAULT 0,
            coupon_reopen_policy  VARCHAR(20) NOT NULL DEFAULT 'NEVER_REOPEN',
            status                VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
            customer_id           UUID REFERENCES customers(id),
            expires_at            TIMESTAMPTZ,
            created_at            TIMESTAMPTZ DEFAULT now(),
            UNIQUE (company_id, code)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_coupons_company_id ON coupons (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_coupons_promotion_id ON coupons (promotion_id)"
    ))

    # 3. coupon_redemptions
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS coupon_redemptions (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id       UUID NOT NULL REFERENCES companies(id),
            coupon_id        UUID NOT NULL REFERENCES coupons(id),
            customer_id      UUID REFERENCES customers(id),
            payment_id       UUID NOT NULL REFERENCES payments(payment_id),
            redeemed_at      TIMESTAMPTZ DEFAULT now(),
            reverted_at      TIMESTAMPTZ,
            reverted_reason  VARCHAR(255)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_coupon_redemptions_company_id "
        "ON coupon_redemptions (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_coupon_redemptions_payment "
        "ON coupon_redemptions (company_id, payment_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_coupon_redemptions_coupon_customer "
        "ON coupon_redemptions (coupon_id, customer_id)"
    ))

    # 4. discount_applications (Decisão D1)
    #    promotion_id NULLABLE: manual-discount cria aplicação sem promoção.
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS discount_applications (
            id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                  UUID NOT NULL REFERENCES companies(id),
            payment_id                  UUID NOT NULL REFERENCES payments(payment_id),
            promotion_id                UUID REFERENCES promotions(id),
            sequence                    INTEGER NOT NULL,
            discount_type               VARCHAR(30) NOT NULL,
            base_amount_at_application  NUMERIC(15,2) NOT NULL,
            discount_amount             NUMERIC(15,2) NOT NULL,
            reverted_at                 TIMESTAMPTZ,
            created_at                  TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_discount_applications_company_id "
        "ON discount_applications (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_discount_applications_payment "
        "ON discount_applications (company_id, payment_id)"
    ))

    for table in _NEW_TABLES:
        _enable_rls(table)

    # 5. payments: coupon_code (manual_override_count já existe — w1x2y3z4a5b6)
    op.execute(sa.text("""
        ALTER TABLE payments
          ADD COLUMN IF NOT EXISTS coupon_code VARCHAR(50)
    """))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE payments DROP COLUMN IF EXISTS coupon_code"))
    op.execute(sa.text("DROP TABLE IF EXISTS discount_applications"))
    op.execute(sa.text("DROP TABLE IF EXISTS coupon_redemptions"))
    op.execute(sa.text("DROP TABLE IF EXISTS coupons"))
    op.execute(sa.text("DROP TABLE IF EXISTS promotions"))
