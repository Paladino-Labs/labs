"""conversation_messages — inbox de atendimento humano

Revision ID: e0s27a_conversation_messages
Revises: e0s20a_intent_classifications
Create Date: 2026-06-13

Sprint 2.7 — Inbox de atendimento humano + estado RESOLVIDA:
  Persiste mensagens por sessão (INBOUND/OUTBOUND) enquanto a conversa está
  em atendimento humano (state=HUMANO). Permite ao atendente ver o histórico
  e responder pelo painel. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s27a_conversation_messages"
down_revision: Union[str, Sequence[str], None] = "e0s20a_intent_classifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS conversation_messages (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id           UUID NOT NULL REFERENCES companies(id),
            session_id           UUID NOT NULL REFERENCES bot_sessions(id),
            -- INBOUND (cliente→sistema) | OUTBOUND (sistema→cliente)
            direction            VARCHAR(10) NOT NULL,
            content              TEXT NOT NULL,
            -- TEXT | BUTTON | LIST | IMAGE
            content_type         VARCHAR(20) NOT NULL DEFAULT 'TEXT',
            -- CLIENT | BOT | AGENT (atendente humano)
            sender_type          VARCHAR(20) NOT NULL,
            -- preenchido quando sender_type=AGENT
            agent_user_id        UUID REFERENCES users(id),
            -- ID da mensagem no WhatsApp (para deduplicação)
            whatsapp_message_id  VARCHAR(100),
            created_at           TIMESTAMPTZ DEFAULT now()
        )
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_session
          ON conversation_messages (session_id, created_at ASC)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_conversation_messages_company
          ON conversation_messages (company_id, created_at DESC)
    """))

    op.execute(sa.text("ALTER TABLE conversation_messages ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON conversation_messages
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))

    # ── Seed do template conversation.escalated para tenants existentes ───────
    # Idempotente (NOT EXISTS) — tenants novos já recebem via create_company.
    _wa_body = (
        "Nova conversa escalada para atendimento humano.\n"
        "Cliente: {{customer_name}} ({{phone}}).\n"
        "Acesse o painel para responder: {{panel_url}}"
    )
    _email_body = (
        "Nova conversa escalada para atendimento humano.\n\n"
        "Cliente: {{customer_name}}\n"
        "Telefone: {{phone}}\n\n"
        "Acesse o painel para responder: {{panel_url}}"
    )
    for channel, body in (("WHATSAPP", _wa_body), ("EMAIL", _email_body)):
        op.execute(sa.text("""
            INSERT INTO communication_templates
                (template_id, company_id, event_type, channel, audience,
                 body_template, is_default, is_active)
            SELECT
                gen_random_uuid(), c.id, 'conversation.escalated',
                :channel, 'OWNER', :body, true, true
            FROM companies c
            WHERE NOT EXISTS (
                SELECT 1 FROM communication_templates ct
                WHERE ct.company_id = c.id
                  AND ct.event_type = 'conversation.escalated'
                  AND ct.channel    = :channel
                  AND ct.audience   = 'OWNER'
            )
        """).bindparams(channel=channel, body=body))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS conversation_messages"))
