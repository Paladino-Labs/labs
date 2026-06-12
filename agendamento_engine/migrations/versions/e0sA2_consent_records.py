"""consent_records — consentimentos LGPD append-only

Revision ID: e0sA2_consent_records
Revises: e0sA1_paladino_identities
Create Date: 2026-06-11

Sprint A — Identidade Paladino (2/3):
  Registro append-only de consentimentos (nunca UPDATE/DELETE).
  company_id NULL = consent global Paladino-wide.
  RLS habilitado sem policy (mesmo padrão de paladino_identities) —
  o vínculo primário é identity_id (global), não company_id;
  acesso exclusivamente via service layer.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sA2_consent_records"
down_revision: Union[str, Sequence[str], None] = "e0sA1_paladino_identities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS consent_records (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            identity_id     UUID NOT NULL REFERENCES paladino_identities(id),
            company_id      UUID REFERENCES companies(id),
            consent_type    VARCHAR(30) NOT NULL,
            channel         VARCHAR(20),
            status          VARCHAR(10) NOT NULL,
            source_channel  VARCHAR(20) NOT NULL,
            occurred_at     TIMESTAMPTZ DEFAULT now(),
            notes           TEXT
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_consent_records_identity_type_channel "
        "ON consent_records (identity_id, consent_type, channel)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_consent_records_company "
        "ON consent_records (company_id) WHERE company_id IS NOT NULL"
    ))

    # Append-only: bloquear UPDATE/DELETE no banco (padrão audit_logs/movements)
    op.execute(sa.text("""
        CREATE OR REPLACE FUNCTION prevent_consent_record_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'consent_records é append-only — % não permitido', TG_OP;
        END;
        $$ LANGUAGE plpgsql
    """))
    op.execute(sa.text("""
        CREATE TRIGGER consent_records_no_update
        BEFORE UPDATE OR DELETE ON consent_records
        FOR EACH ROW EXECUTE FUNCTION prevent_consent_record_modification()
    """))

    # RLS habilitado sem policy — acesso via service layer (ver docstring)
    op.execute(sa.text(
        "ALTER TABLE consent_records ENABLE ROW LEVEL SECURITY"
    ))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS consent_records"))
    op.execute(sa.text(
        "DROP FUNCTION IF EXISTS prevent_consent_record_modification()"
    ))
