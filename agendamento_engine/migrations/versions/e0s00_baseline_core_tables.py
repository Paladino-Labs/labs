"""baseline: tabelas núcleo pré-Alembic (estado legado, anterior à cadeia)

Revision ID: e0s00_baseline_core_tables
Revises:
Create Date: 2026-07-07

NUNCA executar (upgrade) em produção — produção já possui estas tabelas e
está carimbada em revisão descendente (e0s29+). Esta migration existe para
que um banco VAZIO reproduza o schema completo via `alembic upgrade head`.

Cria as 12 tabelas núcleo que existiam ANTES do Alembic, no shape LEGADO
(pré-cadeia). A própria cadeia as transforma até o shape atual de produção:
  - clients        → renomeada para customers (f3a9e1d72b04)
  - blocked_slots  → renomeada para schedule_blocks (f3a9e1d72b04)
  - appointments.financial_status TEXT legada → dropada (540331d2c848) e
    recriada (a8c81686f38e)
  - constraints legadas (clients_phone_key, unique_idempotency_per_company,
    professional_services_professional_id_service_id_key,
    idx_appointments_conflict, appointments_status_check lowercase) →
    dropadas/recriadas pelas migrations de alinhamento
  - working_hours: produção diverge do create_table de 36e2e1f526da
    (default gen_random_uuid + FKs, sem índices ix_*) — shape real de
    produção definido aqui; 36e2e1f526da vira no-op (guard de existência)

RLS/policies NÃO são criadas aqui — vêm da cadeia (h1i2j3k4l5m6,
22bfd8bf16b3, i1j2k3l4m5n6).

validate_status_transition(): função órfã pré-Alembic (nenhum trigger a
usa hoje) — recriada por paridade com produção.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "e0s00_baseline_core_tables"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Extensões exigidas pelos objetos da baseline (EXCLUDE gist sobre UUID
    # exige btree_gist; defaults uuid_generate_v4 exigem uuid-ossp).
    # a9b1c2d3e4f5 também cria btree_gist com IF NOT EXISTS — compatível.
    op.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
    op.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))

    op.execute(text("""
        CREATE TABLE companies (
            id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR NOT NULL
        )
    """))

    # users: sem FK em company_id (paridade com produção — nunca existiu).
    # created_at legada é dropada por 540331d2c848 e recriada por c7b2f4e91a30.
    op.execute(text("""
        CREATE TABLE users (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id    UUID NOT NULL,
            email         VARCHAR NOT NULL CONSTRAINT users_email_key UNIQUE,
            password_hash VARCHAR NOT NULL,
            is_admin      BOOLEAN DEFAULT true,
            created_at    TIMESTAMPTZ DEFAULT now()
        )
    """))

    # clients: renomeada para customers por f3a9e1d72b04 (PK/FK mantêm o
    # nome legado clients_* em produção). clients_phone_key UNIQUE(phone)
    # é a constraint errada de multi-tenant, dropada por f1e2d3c4b5a6.
    op.execute(text("""
        CREATE TABLE clients (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR NOT NULL,
            phone      VARCHAR NOT NULL CONSTRAINT clients_phone_key UNIQUE,
            email      VARCHAR,
            company_id UUID NOT NULL
                       CONSTRAINT clients_company_id_fkey REFERENCES companies(id)
        )
    """))

    op.execute(text("""
        CREATE TABLE professionals (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR NOT NULL,
            active     BOOLEAN DEFAULT true,
            company_id UUID NOT NULL
                       CONSTRAINT professionals_company_id_fkey REFERENCES companies(id)
        )
    """))

    op.execute(text("""
        CREATE TABLE services (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name       VARCHAR NOT NULL,
            price      NUMERIC(10,2) NOT NULL,
            duration   INTEGER NOT NULL,
            active     BOOLEAN DEFAULT true,
            company_id UUID NOT NULL
                       CONSTRAINT services_company_id_fkey REFERENCES companies(id)
        )
    """))

    # professional_services: UNIQUE legada dropada por 540331d2c848;
    # company_id é adicionada por d8e3c2b51f70.
    op.execute(text("""
        CREATE TABLE professional_services (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            professional_id       UUID NOT NULL
                CONSTRAINT professional_services_professional_id_fkey
                REFERENCES professionals(id),
            service_id            UUID NOT NULL
                CONSTRAINT professional_services_service_id_fkey
                REFERENCES services(id),
            commission_percentage NUMERIC(5,2),
            CONSTRAINT professional_services_professional_id_service_id_key
                UNIQUE (professional_id, service_id)
        )
    """))

    # company_settings: sem FK em company_id (paridade com produção).
    op.execute(text("""
        CREATE TABLE company_settings (
            id                            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id                    UUID NOT NULL
                CONSTRAINT company_settings_company_id_key UNIQUE,
            default_commission_percentage NUMERIC(5,2) NOT NULL DEFAULT 40.00
        )
    """))

    # appointments (shape legado):
    #   - financial_status TEXT 'pending' → dropada por 540331d2c848
    #   - appointments_status_check lowercase → recriada por f3a9e1d72b04
    #   - unique_idempotency_per_company → substituída por uq_idempotency
    #   - no_overlapping_appointments sem WHERE → recriada com WHERE por f3a9
    #   - idx_appointments_conflict → dropado por 540331d2c848
    op.execute(text("""
        CREATE TABLE appointments (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            professional_id  UUID NOT NULL
                CONSTRAINT appointments_professional_id_fkey REFERENCES professionals(id),
            client_id        UUID NOT NULL
                CONSTRAINT appointments_client_id_fkey REFERENCES clients(id),
            company_id       UUID NOT NULL
                CONSTRAINT appointments_company_id_fkey REFERENCES companies(id),
            start_at         TIMESTAMPTZ NOT NULL,
            end_at           TIMESTAMPTZ NOT NULL,
            subtotal_amount  NUMERIC(10,2) NOT NULL,
            discount_amount  NUMERIC(10,2) NOT NULL DEFAULT 0,
            total_amount     NUMERIC(10,2) NOT NULL,
            status           VARCHAR NOT NULL,
            version          INTEGER NOT NULL DEFAULT 1,
            idempotency_key  VARCHAR NOT NULL,
            total_commission NUMERIC(10,2) NOT NULL DEFAULT 0,
            financial_status TEXT NOT NULL DEFAULT 'pending',
            CONSTRAINT appointments_status_check CHECK (
                status = ANY (ARRAY['pending'::text, 'confirmed'::text,
                                    'cancelled'::text, 'completed'::text,
                                    'no_show'::text])
            ),
            CONSTRAINT unique_idempotency_per_company
                UNIQUE (company_id, idempotency_key),
            CONSTRAINT no_overlapping_appointments EXCLUDE USING gist (
                professional_id WITH =,
                tstzrange(start_at, end_at) WITH &&
            )
        )
    """))
    op.execute(text("""
        CREATE INDEX idx_appointments_conflict
            ON appointments (professional_id, start_at, end_at)
            WHERE status = ANY (ARRAY['pending'::text, 'confirmed'::text])
    """))

    # appointment_services: company_id + fk_appointment_services_company são
    # dropadas por 540331d2c848 (que também recria as FKs com os nomes/regras
    # atuais de produção).
    op.execute(text("""
        CREATE TABLE appointment_services (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            appointment_id    UUID NOT NULL
                CONSTRAINT appointment_services_appointment_id_fkey
                REFERENCES appointments(id) ON DELETE CASCADE,
            service_id        UUID,
            service_name      VARCHAR NOT NULL,
            duration_snapshot NUMERIC NOT NULL,
            price_snapshot    NUMERIC(10,2) NOT NULL,
            company_id        UUID NOT NULL
                CONSTRAINT fk_appointment_services_company REFERENCES companies(id)
        )
    """))

    # appointment_status_log: company_id/changed_by são dropadas por
    # 540331d2c848 e recriadas por f3a9e1d72b04 (com note). from_status /
    # to_status já no shape final (16014789aa88 usa ADD IF NOT EXISTS).
    op.execute(text("""
        CREATE TABLE appointment_status_log (
            id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            appointment_id UUID NOT NULL
                CONSTRAINT appointment_status_log_appointment_id_fkey
                REFERENCES appointments(id) ON DELETE CASCADE,
            company_id     UUID NOT NULL
                CONSTRAINT fk_status_log_company REFERENCES companies(id),
            changed_by     UUID,
            from_status    VARCHAR,
            to_status      VARCHAR NOT NULL,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))

    # blocked_slots: renomeada para schedule_blocks por f3a9e1d72b04 (PK e
    # índices mantêm nomes blocked_slots_* em produção). Sem FKs (paridade).
    op.execute(text("""
        CREATE TABLE blocked_slots (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            company_id      UUID NOT NULL,
            professional_id UUID NOT NULL,
            start_at        TIMESTAMPTZ NOT NULL,
            end_at          TIMESTAMPTZ NOT NULL,
            reason          VARCHAR(100),
            CONSTRAINT exclude_overlapping_blocks EXCLUDE USING gist (
                company_id WITH =,
                professional_id WITH =,
                tstzrange(start_at, end_at) WITH &&
            )
        )
    """))

    # working_hours: shape REAL de produção (difere do create_table de
    # 36e2e1f526da, que vira no-op via guard). uq_working_hours_day nunca
    # persiste: 16014789aa88 a cria, d1e2f3g4h5i6 a dropa.
    op.execute(text("""
        CREATE TABLE working_hours (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL
                CONSTRAINT working_hours_company_id_fkey REFERENCES companies(id),
            professional_id UUID NOT NULL
                CONSTRAINT working_hours_professional_id_fkey REFERENCES professionals(id),
            weekday         INTEGER NOT NULL,
            opening_time    TIME NOT NULL,
            closing_time    TIME NOT NULL,
            is_active       BOOLEAN DEFAULT true
        )
    """))

    # Função órfã pré-Alembic (nenhum trigger a referencia) — paridade.
    op.execute(text("""
        CREATE OR REPLACE FUNCTION public.validate_status_transition()
         RETURNS trigger
         LANGUAGE plpgsql
        AS $function$
        BEGIN
            -- Só valida se o status mudou
            IF NEW.status IS DISTINCT FROM OLD.status THEN

                IF OLD.status = 'pending' AND NEW.status NOT IN ('confirmed', 'cancelled') THEN
                    RAISE EXCEPTION 'Transição inválida';
                END IF;

                IF OLD.status = 'confirmed' AND NEW.status NOT IN ('completed', 'no_show', 'cancelled') THEN
                    RAISE EXCEPTION 'Transição inválida';
                END IF;

                IF OLD.status IN ('completed', 'cancelled', 'no_show') THEN
                    RAISE EXCEPTION 'Não é possível alterar estado final';
                END IF;

            END IF;

            RETURN NEW;
        END;
        $function$
    """))


def downgrade() -> None:
    op.execute(text("DROP FUNCTION IF EXISTS public.validate_status_transition()"))
    # Nomes pós-rename (customers/schedule_blocks) cobertos com IF EXISTS.
    for t in (
        "working_hours", "blocked_slots", "schedule_blocks",
        "appointment_status_log", "appointment_services", "appointments",
        "company_settings", "professional_services", "services",
        "professionals", "clients", "customers", "users", "companies",
    ):
        op.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
