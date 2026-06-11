"""add_payment_submethod — persiste o submethod no Payment

Revision ID: m5n6o7p8q9r0
Revises: l4m5n6o7p8q9
Create Date: 2026-06-10

Adiciona payments.payment_submethod (VARCHAR(50), nullable).
Permite que confirm_manual use o submethod registrado na criação do
pagamento quando o body do confirm-manual não o envia — evitando o
fallback MAQUININHA_CREDIT_OUTROS para pagamentos criados com bandeira.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "m5n6o7p8q9r0"
down_revision: Union[str, Sequence[str], None] = "l4m5n6o7p8q9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column("payment_submethod", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "payment_submethod")
