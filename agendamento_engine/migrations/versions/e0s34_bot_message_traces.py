"""bot_message_traces — telemetria ponta a ponta do bot (S-bot-1)

Revision ID: e0s34_bot_message_traces
Revises: e0s33_worker_heartbeats
Create Date: 2026-08-07

Uma linha por evento inbound do webhook da Evolution, com a trajetória
completa: webhook → classificador → dispatcher → saída.

⚠️ TABELA DESCARTÁVEL. Retenção de 30 dias, expurgo oportunista no próprio
processo (app/modules/whatsapp/trace.py) — o beat NÃO existe em produção e
fazer o webhook do bot depender do worker Celery foi o incidente de 22/07.

⚠️ company_id é NULLABLE de propósito: eventos descartados ANTES de resolver o
tenant (instância desconhecida, JSON inválido, grupo) são exatamente os que
hoje somem sem rastro. A policy de RLS admite `company_id IS NULL` pelo mesmo
motivo — sem isso a linha ficaria invisível justamente na investigação.

⚠️ Cadeia: descende de e0s33_worker_heartbeats (head único). Conferido com
`alembic heads` — ver a seção "Bifurcação de cadeia" no CLAUDE.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s34_bot_message_traces"
down_revision: Union[str, Sequence[str], None] = "e0s33_worker_heartbeats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bot_message_traces (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            -- NULLABLE: evento descartado antes de resolver o tenant
            company_id       UUID REFERENCES companies(id),
            received_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            instance_name    VARCHAR(200),
            event            VARCHAR(40),
            -- pseudônimo estável do interlocutor (sha256 truncado): agrupa sem
            -- gravar outra cópia legível do telefone do cliente final
            whatsapp_hash    VARCHAR(32),
            whatsapp_masked  VARCHAR(60),
            message_id       VARCHAR(255),
            message_type     VARCHAR(60),

            session_id       UUID,
            fsm_state        VARCHAR(40),
            fsm_state_after  VARCHAR(40),
            -- PROCESSED | IGNORED_* | REJECTED_UNAUTHORIZED | ERROR
            outcome          VARCHAR(40) NOT NULL,
            user_input       TEXT,

            webhook          JSONB NOT NULL DEFAULT '{}',
            classifier       JSONB NOT NULL DEFAULT '{}',
            dispatch         JSONB NOT NULL DEFAULT '{}',
            outbound         JSONB NOT NULL DEFAULT '[]',
            duration_ms      INTEGER
        )
    """))

    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_traces_company_at
          ON bot_message_traces (company_id, received_at DESC)
    """))
    # Leitura por conversa: os eventos de um mesmo interlocutor em ordem.
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_traces_wa_at
          ON bot_message_traces (whatsapp_hash, received_at DESC)
    """))
    # Usado pelo expurgo da retenção — sem ele o DELETE varre a tabela.
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_traces_received_at
          ON bot_message_traces (received_at)
    """))
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_traces_outcome
          ON bot_message_traces (outcome, received_at DESC)
    """))

    op.execute(sa.text("""
        COMMENT ON TABLE bot_message_traces IS
        'Telemetria ponta a ponta do bot (S-bot-1). Instrumento descartável, '
        'retenção 30 dias com expurgo oportunista em whatsapp/trace.py. '
        'Telefone do cliente NUNCA em claro: whatsapp_masked + whatsapp_hash.'
    """))

    op.execute(sa.text("ALTER TABLE bot_message_traces ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON bot_message_traces
          USING (
            company_id IS NULL
            OR company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
          WITH CHECK (
            company_id IS NULL
            OR company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS bot_message_traces"))
