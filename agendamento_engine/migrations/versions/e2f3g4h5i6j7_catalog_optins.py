"""catalog_optins

Revision ID: e2f3g4h5i6j7
Revises: j2k3l4m5n6o7
Create Date: 2026-06-07

Sprint 11 — Catálogo opt-ins:
  1. Tempos de preparo em services (preparation_minutes_before/after)
  2. business_hours_structured em company_profiles (JSONB)
  3. Fix FK AppointmentService.service_id → ON DELETE SET NULL
  4. Nova tabela service_pricing_overrides (com RLS)
  5. Nova tabela service_variants (com RLS)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3g4h5i6j7"
down_revision: Union[str, Sequence[str], None] = "j2k3l4m5n6o7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Tempos de preparo em services
    op.execute(sa.text("""
        ALTER TABLE services
            ADD COLUMN IF NOT EXISTS preparation_minutes_before INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS preparation_minutes_after  INTEGER NOT NULL DEFAULT 0
    """))

    # 2. business_hours estruturado em company_profiles
    op.execute(sa.text("""
        ALTER TABLE company_profiles
            ADD COLUMN IF NOT EXISTS business_hours_structured JSONB
    """))

    # 3. Fix FK AppointmentService.service_id — ON DELETE SET NULL
    op.execute(sa.text("""
        ALTER TABLE appointment_services
            DROP CONSTRAINT IF EXISTS appointment_services_service_id_fkey,
            ADD CONSTRAINT appointment_services_service_id_fkey
                FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE SET NULL
    """))

    # 4. ServicePricingOverride
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS service_pricing_overrides (
            override_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id),
            professional_id UUID NOT NULL REFERENCES professionals(id),
            service_id      UUID NOT NULL REFERENCES services(id),
            price           NUMERIC(10,2) NOT NULL CHECK (price >= 0),
            duration_min    INTEGER,
            is_active       BOOLEAN NOT NULL DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ,
            UNIQUE(professional_id, service_id)
        )
    """))
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'service_pricing_overrides'
                  AND policyname = 'tenant_isolation'
            ) THEN
                CREATE POLICY tenant_isolation ON service_pricing_overrides
                    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
            END IF;
        END $$
    """))
    op.execute(sa.text("ALTER TABLE service_pricing_overrides ENABLE ROW LEVEL SECURITY"))

    # 5. ServiceVariant
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS service_variants (
            variant_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id),
            service_id      UUID NOT NULL REFERENCES services(id),
            name            VARCHAR NOT NULL,
            price           NUMERIC(10,2) NOT NULL CHECK (price >= 0),
            duration_min    INTEGER NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT true,
            sort_order      INTEGER NOT NULL DEFAULT 0,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ
        )
    """))
    op.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'service_variants'
                  AND policyname = 'tenant_isolation'
            ) THEN
                CREATE POLICY tenant_isolation ON service_variants
                    USING (company_id = current_setting('app.company_id', TRUE)::UUID);
            END IF;
        END $$
    """))
    op.execute(sa.text("ALTER TABLE service_variants ENABLE ROW LEVEL SECURITY"))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS service_variants"))
    op.execute(sa.text("DROP TABLE IF EXISTS service_pricing_overrides"))
    op.execute(sa.text("""
        ALTER TABLE appointment_services
            DROP CONSTRAINT IF EXISTS appointment_services_service_id_fkey,
            ADD CONSTRAINT appointment_services_service_id_fkey
                FOREIGN KEY (service_id) REFERENCES services(id)
    """))
    op.execute(sa.text("""
        ALTER TABLE company_profiles DROP COLUMN IF EXISTS business_hours_structured
    """))
    op.execute(sa.text("""
        ALTER TABLE services
            DROP COLUMN IF EXISTS preparation_minutes_before,
            DROP COLUMN IF EXISTS preparation_minutes_after
    """))
