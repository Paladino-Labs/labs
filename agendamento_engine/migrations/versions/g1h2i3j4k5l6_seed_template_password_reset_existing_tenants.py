"""seed: template auth.password_reset_requested para tenants existentes

Revision ID: g1h2i3j4k5l6
Revises: f1g2h3i4j5k6
Create Date: 2026-05-28

Insere o template auth.password_reset_requested para todos os tenants
já existentes que ainda não o possuem.

ON CONFLICT DO NOTHING: idempotente — pode ser re-executado sem efeito colateral.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, Sequence[str], None] = "f1g2h3i4j5k6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BODY_TEMPLATE = (
    "Seu código de redefinição de senha Paladino: {{token}}. "
    "Válido por 15 minutos. Não compartilhe este código."
)


def upgrade() -> None:
    op.execute(text(f"""
        INSERT INTO communication_templates
            (template_id, company_id, event_type, channel, audience,
             body_template, is_default, is_active)
        SELECT
            gen_random_uuid(),
            c.id,
            'auth.password_reset_requested',
            'WHATSAPP',
            'CLIENT',
            '{_BODY_TEMPLATE}',
            true,
            true
        FROM companies c
        WHERE NOT EXISTS (
            SELECT 1
            FROM communication_templates ct
            WHERE ct.company_id = c.id
              AND ct.event_type  = 'auth.password_reset_requested'
              AND ct.channel     = 'WHATSAPP'
              AND ct.audience    = 'CLIENT'
        )
    """))


def downgrade() -> None:
    # Conservador: não remove em downgrade — o template pode estar em uso.
    # Para reverter manualmente: DELETE FROM communication_templates
    #   WHERE event_type = 'auth.password_reset_requested' AND is_default = true;
    pass
