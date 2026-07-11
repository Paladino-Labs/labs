"""intent telemetry — contexto de classificação + desfecho (volante F5a)

Revision ID: e0s30_intent_telemetry
Revises: e0s29_product_sales
Create Date: 2026-07-10

Bot F5a — shadow mode + volante de telemetria:
  1. intent_classifications ganha fsm_state (estado FSM no momento) e
     routing_decision (decisão de roteamento efetivamente tomada — escrita no
     MESMO request da classificação; o modelo append-only entre requests é
     preservado).
  2. intent_outcomes: tabela-irmã 1:1 (UNIQUE classification_id) para o
     desfecho, que chega em request POSTERIOR — INSERT aqui em vez de UPDATE
     na classificação mantém intent_classifications append-only por convenção.
     Classificação sem linha aqui = desfecho PENDING (LEFT JOIN na análise).
  RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s30_intent_telemetry"
down_revision: Union[str, Sequence[str], None] = "e0s29_product_sales"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        ALTER TABLE intent_classifications
          ADD COLUMN IF NOT EXISTS fsm_state VARCHAR(40),
          ADD COLUMN IF NOT EXISTS routing_decision VARCHAR(30)
    """))

    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS intent_outcomes (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id),
            classification_id  UUID NOT NULL UNIQUE
                               REFERENCES intent_classifications(id) ON DELETE CASCADE,
            -- MENU_CLICK_AFTER_FALLBACK | FLOW_CONFIRMED | FLOW_CANCELLED | ABANDONED
            outcome            VARCHAR(40) NOT NULL,
            -- ex.: {"menu_option": "opt_agendar"} | {"appointment_id": "..."}
            outcome_detail     JSONB NOT NULL DEFAULT '{}',
            outcome_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_intent_outcomes_company_at
          ON intent_outcomes (company_id, outcome_at DESC)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_intent_outcomes_company_outcome
          ON intent_outcomes (company_id, outcome)
    """))

    op.execute(sa.text("ALTER TABLE intent_outcomes ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON intent_outcomes
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
    op.execute(sa.text("DROP TABLE IF EXISTS intent_outcomes"))
    op.execute(sa.text("""
        ALTER TABLE intent_classifications
          DROP COLUMN IF EXISTS routing_decision,
          DROP COLUMN IF EXISTS fsm_state
    """))
