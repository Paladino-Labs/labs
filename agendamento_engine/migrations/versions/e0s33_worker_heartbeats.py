"""worker_heartbeats — batimento do worker Celery (S-heartbeat)

Revision ID: e0s33_worker_heartbeats
Revises: e0s32_bot_conversation_leases
Create Date: 2026-08-05

Tabela de PLATAFORMA (sem company_id, sem RLS — mesmo padrão de
platform_settings): o batimento descreve o processo, não um tenant.

⚠️ Por que TABELA e não Redis:
  1. O Redis é justamente o que cai. Medir a saúde da fila por um estado que
     mora no componente sob suspeita é ficar cego no momento errado. O Postgres
     é a dependência sem a qual nada funciona.
  2. Nada neste sistema pode depender de estado de SESSÃO do Postgres — o pooler
     em transaction-mode não o preserva (provado no S2.1, advisory lock).
     Uma linha é pooler-agnóstica por construção.

⚠️ Quem escreve é o WORKER, nunca o beat. Beat vivo com worker morto foi o modo
de falha de 22/07; um heartbeat escrito pelo beat mentiria exatamente nesse caso.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s33_worker_heartbeats"
down_revision: Union[str, Sequence[str], None] = "e0s32_bot_conversation_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS worker_heartbeats (
            -- hostname do worker Celery ("celery@<host>"): uma linha por processo.
            worker_name    VARCHAR(200) PRIMARY KEY,
            -- instante em que a task de batimento EXECUTOU (relógio do worker).
            last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- instante em que o batimento foi DESPACHADO à fila.
            -- last_seen_at - dispatched_at = latência real da fila.
            dispatched_at  TIMESTAMPTZ,
            queue_lag_ms   INTEGER,
            pid            INTEGER,
            beat_count     BIGINT NOT NULL DEFAULT 0,
            detail         JSONB NOT NULL DEFAULT '{}'
        )
    """))
    op.execute(sa.text("""
        COMMENT ON TABLE worker_heartbeats IS
        'Batimento escrito pelo WORKER Celery (S-heartbeat). Uma linha por processo, '
        'upsert idempotente por worker_name. Lida por GET /health/deep.'
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS worker_heartbeats"))
