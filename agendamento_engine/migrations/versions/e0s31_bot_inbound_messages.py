"""bot_inbound_messages — buffer durável do webhook do bot (S2.1)

Revision ID: e0s31_bot_inbound_messages
Revises: e0s30_intent_telemetry
Create Date: 2026-07-20

S2.1 — Entrega B: desacoplar o webhook do bot do event loop.
  O webhook persiste a mensagem crua (status RECEIVED) antes de responder 200
  e enfileira drain_bot_inbound; o worker processa fora do event loop único.
  UNIQUE (company_id, whatsapp_message_id) = dedup durável (re-entrega da
  Evolution + retry de fila). RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s31_bot_inbound_messages"
down_revision: Union[str, Sequence[str], None] = "e0s30_intent_telemetry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bot_inbound_messages (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id           UUID NOT NULL REFERENCES companies(id),
            instance_name        VARCHAR(100) NOT NULL,
            -- JID completo do remetente (chave da conversa com company_id)
            whatsapp_id          VARCHAR(100) NOT NULL,
            -- ID da mensagem no WhatsApp — dedup durável
            whatsapp_message_id  VARCHAR(100) NOT NULL,
            -- payload cru do evento (data desembrulhado do batch)
            raw_payload          JSONB NOT NULL,
            -- RECEIVED | PROCESSING | DONE | FAILED
            status               VARCHAR(20) NOT NULL DEFAULT 'RECEIVED',
            attempts             INTEGER NOT NULL DEFAULT 0,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
            processed_at         TIMESTAMPTZ
        )
    """))
    # Dedup durável: re-entrega da Evolution + retry de fila (ON CONFLICT DO NOTHING)
    op.execute(sa.text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_bot_inbound_message_id
          ON bot_inbound_messages (company_id, whatsapp_message_id)
    """))
    # Fila de drain por conversa, ordenada por chegada
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_inbound_conversation
          ON bot_inbound_messages (company_id, whatsapp_id, status, created_at ASC)
    """))

    op.execute(sa.text("ALTER TABLE bot_inbound_messages ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON bot_inbound_messages
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
    op.execute(sa.text("DROP TABLE IF EXISTS bot_inbound_messages"))
