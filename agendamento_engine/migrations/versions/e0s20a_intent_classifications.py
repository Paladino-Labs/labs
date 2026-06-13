"""intent_classifications — log auditável do IntentClassifier

Revision ID: e0s20a_intent_classifications
Revises: e0sH1_crm
Create Date: 2026-06-12

Sprint 2.0 — IntentClassifier isolado:
  Toda classificação (REGEX | LLM | FALLBACK) é persistida (invariante 3).
  Append-only por convenção — sem trigger; dados de auditoria.
  RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s20a_intent_classifications"
down_revision: Union[str, Sequence[str], None] = "e0sH1_crm"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS intent_classifications (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id),
            session_id         UUID,
            raw_input          TEXT NOT NULL,
            classified_intent  VARCHAR(50) NOT NULL,
            -- 0.000 a 1.000
            confidence         NUMERIC(4,3) NOT NULL,
            -- REGEX | LLM | FALLBACK
            source             VARCHAR(10) NOT NULL,
            -- entidades extraídas (serviço, data, etc.)
            entities           JSONB NOT NULL DEFAULT '{}',
            -- NULL para REGEX/FALLBACK
            llm_provider       VARCHAR(30),
            llm_model          VARCHAR(50),
            llm_latency_ms     INTEGER,
            classified_at      TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_intent_classifications_company_at
          ON intent_classifications (company_id, classified_at DESC)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_intent_classifications_intent
          ON intent_classifications (company_id, classified_intent)
    """))

    op.execute(sa.text("ALTER TABLE intent_classifications ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON intent_classifications
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
    op.execute(sa.text("DROP TABLE IF EXISTS intent_classifications"))
