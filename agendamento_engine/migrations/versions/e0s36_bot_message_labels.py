"""bot_message_labels — rótulo humano sobre o trace (S-painel-telemetria)

Revision ID: e0s36_bot_message_labels
Revises: e0s35_user_phone
Create Date: 2026-08-13

O Silva lê as conversas dos dias de coleta e, lendo, rotula o que o bot
DEVERIA ter entendido. Esta tabela guarda esse rótulo. É o insumo do
redesenho do catálogo de intenções.

⚠️ Tabela de PLATAFORMA, sem `company_id` e sem RLS — mesmo idioma de
`impersonation_grants` (e0sC2) e `platform_settings` (e0sC3). O rótulo é
julgamento do staff sobre o comportamento do bot, não dado do tenant; o
tenant a que a mensagem pertence continua sendo lido do trace.

⚠️ VIDA ÚTIL ATRELADA AO TRACE. `bot_message_traces` tem retenção de 30 dias
com expurgo oportunista, e o FK é ON DELETE CASCADE: o rótulo morre com a
mensagem que ele rotula. É deliberado — rótulo órfão não é analisável (some o
texto, o estado e a classificação que o justificavam). Quem precisar do
resultado além da janela deve extrair o RESUMO (a query do relatório do
sprint), não preservar a tabela.

⚠️ `expected_intent` é VARCHAR livre, validado só na API — de propósito.
O catálogo de intenções é EXATAMENTE o que este trabalho vai redesenhar;
prendê-lo num enum (ou num CHECK) faria toda ideia nova do Silva exigir uma
migration. `understood` tem CHECK porque seus 3 valores são a pergunta em si,
não o vocabulário em revisão.

⚠️ Cadeia: descende de e0s35_user_phone. Conferido com `alembic heads`
(head único) — ver "Bifurcação de cadeia" no CLAUDE.md.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s36_bot_message_labels"
down_revision: Union[str, Sequence[str], None] = "e0s35_user_phone"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bot_message_labels (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            -- 1 rótulo por mensagem: o UNIQUE é o que torna a gravação da tela
            -- um upsert idempotente (marcar de novo corrige, não duplica).
            trace_id        UUID NOT NULL UNIQUE
                            REFERENCES bot_message_traces(id) ON DELETE CASCADE,

            -- YES | NO | WRONG — "o bot entendeu?"
            understood      VARCHAR(10),
            -- "o que era?" — catálogo vive na API, não aqui (ver docstring)
            expected_intent VARCHAR(40),
            note            TEXT,

            labeled_by      UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

            -- Linha sem NENHUM dos três campos é ruído: a tela apaga o rótulo
            -- em vez de gravar vazio. O CHECK impede que um caminho futuro
            -- reintroduza a linha-fantasma.
            CONSTRAINT chk_bot_message_labels_not_empty CHECK (
                understood IS NOT NULL
                OR expected_intent IS NOT NULL
                OR (note IS NOT NULL AND note <> '')
            ),
            CONSTRAINT chk_bot_message_labels_understood CHECK (
                understood IS NULL OR understood IN ('YES', 'NO', 'WRONG')
            )
        )
    """))

    # Leitura por conversa: a tela busca os rótulos das mensagens de um
    # whatsapp_hash de uma vez (evita N+1 por mensagem aberta).
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_labels_trace
          ON bot_message_labels (trace_id)
    """))
    # Usado pela query de resumo (marcação → contagem por intenção esperada).
    op.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS idx_bot_message_labels_intent
          ON bot_message_labels (expected_intent)
          WHERE expected_intent IS NOT NULL
    """))

    op.execute(sa.text("""
        COMMENT ON TABLE bot_message_labels IS
        'Rótulo humano sobre bot_message_traces (S-painel-telemetria). '
        'Tabela de plataforma, sem RLS. CASCADE do trace: o rótulo tem a '
        'mesma vida útil de 30 dias da mensagem que rotula.'
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS bot_message_labels"))
