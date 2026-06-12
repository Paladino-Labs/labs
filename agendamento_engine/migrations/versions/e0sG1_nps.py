"""nps_configs + nps_surveys + nps_responses

Revision ID: e0sG1_nps
Revises: e0sC3_platform_settings
Create Date: 2026-06-12

Sprint G — NPS pós-atendimento:
  1. nps_configs   — configuração por tenant (1:1 com companies): canal,
     delay após operation.completed, intervalo mínimo entre pesquisas ao
     mesmo cliente, threshold de alerta de nota baixa
  2. nps_surveys   — pesquisa enviada ao cliente
     (PENDING | SENT | RESPONDED | EXPIRED)
  3. nps_responses — resposta do cliente (score 0–10); append-only no
     sentido de produto: tenant só adiciona tenant_response, nunca edita
     o score (enforced no service layer)
Todas com RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sG1_nps"
down_revision: Union[str, Sequence[str], None] = "e0sC3_platform_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_TABLES = ["nps_configs", "nps_surveys", "nps_responses"]


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
    # 1. nps_configs
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS nps_configs (
            id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id               UUID NOT NULL UNIQUE REFERENCES companies(id),
            enabled                  BOOLEAN NOT NULL DEFAULT true,
            channel                  VARCHAR(20) NOT NULL DEFAULT 'WHATSAPP',
            delay_minutes            INTEGER NOT NULL DEFAULT 30,
            min_interval_days        INTEGER NOT NULL DEFAULT 30,
            low_score_threshold      INTEGER NOT NULL DEFAULT 6,
            low_score_alert_enabled  BOOLEAN NOT NULL DEFAULT true,
            created_at               TIMESTAMPTZ DEFAULT now(),
            updated_at               TIMESTAMPTZ DEFAULT now()
        )
    """))

    # 2. nps_surveys
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS nps_surveys (
            id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id            UUID NOT NULL REFERENCES companies(id),
            customer_id           UUID NOT NULL REFERENCES customers(id),
            appointment_id        UUID NOT NULL REFERENCES appointments(id),
            status                VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            scheduled_for         TIMESTAMPTZ NOT NULL,
            sent_at               TIMESTAMPTZ,
            responded_at          TIMESTAMPTZ,
            expires_at            TIMESTAMPTZ NOT NULL,
            communication_log_id  UUID,
            created_at            TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_nps_surveys_company_id ON nps_surveys (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_nps_surveys_status_scheduled "
        "ON nps_surveys (status, scheduled_for)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_nps_surveys_customer "
        "ON nps_surveys (company_id, customer_id, created_at)"
    ))
    # Idempotência do agendamento: 1 survey por appointment
    op.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_nps_surveys_appointment "
        "ON nps_surveys (appointment_id)"
    ))

    # 3. nps_responses
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS nps_responses (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            survey_id        UUID NOT NULL UNIQUE REFERENCES nps_surveys(id),
            company_id       UUID NOT NULL REFERENCES companies(id),
            score            INTEGER NOT NULL CHECK (score >= 0 AND score <= 10),
            comment          TEXT,
            tenant_response  TEXT,
            responded_at     TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_nps_responses_company_id ON nps_responses (company_id)"
    ))

    for table in _NEW_TABLES:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(_NEW_TABLES):
        op.execute(sa.text(f"DROP TABLE IF EXISTS {table} CASCADE"))
