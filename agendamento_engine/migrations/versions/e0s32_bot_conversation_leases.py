"""bot_conversation_leases — lease por conversa (pooler-agnóstico, S2.1 fix)

Revision ID: e0s32_bot_conversation_leases
Revises: e0s31_bot_inbound_messages
Create Date: 2026-07-21

S2.1 — Entrega B (fix): a serialização por conversa do drain NÃO pode usar
advisory lock de sessão. O pooler transaction-mode do Supabase (porta 6543) não
preserva estado de sessão entre transações — provado empiricamente: dois workers
adquirem o MESMO advisory lock (exclusão mútua evapora). É o mesmo mecanismo do
vazamento de set_config da RLS (auditoria A-ISO/RLS×Pooler).

Lease em tabela: claim atômico via INSERT ON CONFLICT DO UPDATE ... WHERE
locked_until < now() RETURNING — cada operação é uma transação única, portanto
funciona em QUALQUER modo de pooler. Expiração da lease = recuperação de crash
embutida. RLS canônico app.current_company_id.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s32_bot_conversation_leases"
down_revision: Union[str, Sequence[str], None] = "e0s31_bot_inbound_messages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS bot_conversation_leases (
            company_id   UUID NOT NULL REFERENCES companies(id),
            whatsapp_id  VARCHAR(100) NOT NULL,
            -- id do detentor: host:pid:task_id
            locked_by    VARCHAR(200) NOT NULL,
            locked_until TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (company_id, whatsapp_id)
        )
    """))

    op.execute(sa.text("ALTER TABLE bot_conversation_leases ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON bot_conversation_leases
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
    op.execute(sa.text("DROP TABLE IF EXISTS bot_conversation_leases"))
