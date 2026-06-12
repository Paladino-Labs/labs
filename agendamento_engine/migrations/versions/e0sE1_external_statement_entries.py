"""external_statement_entries — conciliação com extrato externo

Revision ID: e0sE1_external_statement_entries
Revises: e0s16a_promotions_coupons
Create Date: 2026-06-11

Sprint E — ExternalStatementEntry:
  1. external_statement_entries — linha importada de extrato externo (CSV):
     status PENDING | MATCHED | DISMISSED; matched_movement_id é vínculo
     UNIDIRECIONAL (Movement nunca é alterado — append-only preservado)
  2. UNIQUE (company_id, line_hash) — idempotência de re-upload
     (line_hash = SHA-256 da linha crua do CSV)
  3. RLS canônico app.current_company_id
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0sE1_external_statement_entries"
down_revision: Union[str, Sequence[str], None] = "e0s16a_promotions_coupons"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS external_statement_entries (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id           UUID NOT NULL REFERENCES companies(id),
            account_id           UUID NOT NULL REFERENCES accounts(account_id),
            occurred_at          DATE NOT NULL,
            amount               NUMERIC(15,2) NOT NULL,
            direction            VARCHAR(10) NOT NULL,
            description          VARCHAR(500),
            raw_line             TEXT,
            line_hash            VARCHAR(64) NOT NULL,
            status               VARCHAR(20) NOT NULL DEFAULT 'PENDING',
            matched_movement_id  UUID REFERENCES movements(movement_id),
            dismissed_reason     VARCHAR(255),
            dismissed_at         TIMESTAMPTZ,
            dismissed_by         UUID REFERENCES users(id),
            imported_at          TIMESTAMPTZ DEFAULT now(),
            import_batch_id      UUID NOT NULL,
            UNIQUE (company_id, line_hash)
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_external_statement_entries_company_id "
        "ON external_statement_entries (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_external_statement_entries_company_status "
        "ON external_statement_entries (company_id, status)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_external_statement_entries_batch "
        "ON external_statement_entries (company_id, import_batch_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_external_statement_entries_matched_movement "
        "ON external_statement_entries (matched_movement_id)"
    ))

    op.execute(sa.text(
        "ALTER TABLE external_statement_entries ENABLE ROW LEVEL SECURITY"
    ))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON external_statement_entries
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS external_statement_entries"))
