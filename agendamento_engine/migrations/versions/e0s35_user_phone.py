"""users.phone + user_invitations.phone — telefone na cadeia do convite (S-plataforma-whatsapp)

Revision ID: e0s35_user_phone
Revises: e0s34_bot_message_traces
Create Date: 2026-08-11

Os três eventos de plataforma (convite, reset de senha, escalada de conversa)
precisam de um destinatário WhatsApp. Não havia telefone em NENHUM ponto da
cadeia: nem no `User`, nem no `UserInvitation`, nem no `InviteUserRequest`.

⚠️ `Company.owner_mobile_phone` NÃO serve — é o telefone do dono da empresa, e
`invite_user` convida também ADMIN, OPERATOR e PROFESSIONAL. Usá-lo mandaria o
link de ativação da conta de outra pessoa para o WhatsApp do dono (caminho de
tomada de conta). O telefone precisa ser do CONVIDADO, e por isso nasce aqui.

⚠️ As duas colunas são NULLABLE no banco, e o convite exige telefone na CAMADA
DE API (`InviteUserRequest.phone`). Motivo: os usuários e convites que já
existem não têm telefone e o Silva vai preenchê-los por SQL. NOT NULL exigiria
um default sintético — um telefone inventado é pior que a ausência, porque o
`dispatch` tentaria entregar nele.

Formato armazenado: E.164 sem o '+' (ex.: "5562988887777") — mesma convenção de
`customers.phone`, que é o valor que vai para o `evolution_client.send_text`.
Normalização canônica: `identity/resolver.normalize_phone_e164`.

⚠️ Cadeia: descende de e0s34_bot_message_traces (head único).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s35_user_phone"
down_revision: Union[str, Sequence[str], None] = "e0s34_bot_message_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)"
    ))
    op.execute(sa.text(
        "ALTER TABLE user_invitations ADD COLUMN IF NOT EXISTS phone VARCHAR(20)"
    ))
    # Com WHATSAPP na frente da preferência de canal, o dispatch precisa poder
    # registrar "canal ligado, template existe, mas não há endereço" — o caso
    # dos usuários que ainda não têm telefone. Sem um status próprio isso se
    # confundiria com SKIPPED_CHANNEL_DISABLED e a leitura dos logs mentiria.
    #
    # ⚠️ FORA DA TRANSAÇÃO, de propósito. O `env.py` envolve a execução inteira
    # em `context.begin_transaction()`, e `ALTER TYPE ... ADD VALUE` só é aceito
    # dentro de bloco de transação a partir do PostgreSQL 12 — em versões
    # anteriores levanta "cannot run inside a transaction block" e derruba o
    # pre-deploy. O Supabase é PG 15, então funcionaria; mas a conexão em
    # AUTOCOMMIT torna a migration independente da versão, e o custo é uma
    # linha. Não converta de volta para `op.execute` cru.
    #
    # O valor NÃO é usado nesta migration — e não poderia ser: PostgreSQL só
    # permite usar um valor de enum depois que a transação que o criou committa.
    bind = op.get_bind()
    with bind.execution_options(isolation_level="AUTOCOMMIT") as autocommit:
        autocommit.execute(sa.text(
            "ALTER TYPE communicationlogstatus ADD VALUE IF NOT EXISTS "
            "'SKIPPED_NO_RECIPIENT'"
        ))


# ⚠️ O downgrade NÃO remove o valor do enum: PostgreSQL não suporta
# `ALTER TYPE ... DROP VALUE`. Um valor de enum a mais é inerte.


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE user_invitations DROP COLUMN IF EXISTS phone"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS phone"))
