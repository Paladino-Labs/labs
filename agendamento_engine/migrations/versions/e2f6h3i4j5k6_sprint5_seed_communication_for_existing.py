"""sprint5: seed communication_settings e templates para tenants existentes

Revision ID: e2f6h3i4j5k6
Revises: e1f5g2h3i4j5
Create Date: 2026-05-27

Para cada company sem communication_settings: cria registro com defaults.
Para cada company sem templates: cria os 7 templates obrigatórios.
Idempotente via ON CONFLICT DO NOTHING.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e2f6h3i4j5k6"
down_revision: Union[str, Sequence[str], None] = "e1f5g2h3i4j5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_TEMPLATES = [
    {
        "event_type": "appointment.confirmed",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! ✅\n\n"
            "Seu agendamento foi confirmado:\n\n"
            "✂️  *{{servico}}*\n"
            "👤  {{profissional}}\n"
            "📅  {{data}} às {{horario}}\n\n"
            "Te esperamos! Qualquer dúvida, é só responder aqui. 😊"
        ),
    },
    {
        "event_type": "appointment.confirmed",
        "channel": "WHATSAPP",
        "audience": "PROFESSIONAL",
        "body_template": (
            "Novo agendamento confirmado!\n\n"
            "👤  Cliente: {{cliente_nome}}\n"
            "✂️  Serviço: {{servico}}\n"
            "📅  {{data}} às {{horario}}"
        ),
    },
    {
        "event_type": "appointment.cancelled",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}. 😔\n\n"
            "Seu agendamento de *{{servico}}* no dia {{data}} às {{horario}} "
            "foi cancelado.\n\nPara reagendar, é só responder aqui."
        ),
    },
    {
        "event_type": "appointment.reminder_24h",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! 👋\n\n"
            "Lembrete: você tem *{{servico}}* com *{{profissional}}* "
            "amanhã, {{data}} às {{horario}}. 💈\n\n"
            "Responda _Ver agendamentos_ para gerenciar."
        ),
    },
    {
        "event_type": "appointment.reminder_2h",
        "channel": "WHATSAPP",
        "audience": "CLIENT",
        "body_template": (
            "Olá, {{cliente_nome}}! 😊\n\n"
            "Seu *{{servico}}* começa em 2 horas, às {{horario}}. Te esperamos! 💈"
        ),
    },
    {
        "event_type": "appointment.no_show",
        "channel": "WHATSAPP",
        "audience": "PROFESSIONAL",
        "body_template": (
            "Atenção: o cliente {{cliente_nome}} não compareceu ao agendamento "
            "de *{{servico}}* às {{horario}} do dia {{data}}."
        ),
    },
    {
        "event_type": "appointment.no_show",
        "channel": "WHATSAPP",
        "audience": "OWNER",
        "body_template": (
            "No-show registrado: {{cliente_nome}} — *{{servico}}* "
            "com {{profissional}} às {{horario}} do dia {{data}}."
        ),
    },
]


def upgrade() -> None:
    conn = op.get_bind()

    companies = conn.execute(sa.text("SELECT id FROM companies")).fetchall()

    for row in companies:
        company_id = row[0]

        # CommunicationSettings — idempotente
        conn.execute(sa.text("""
            INSERT INTO communication_settings
                (settings_id, company_id, whatsapp_enabled, email_enabled,
                 quiet_hours_enabled, quiet_hours_start, quiet_hours_end,
                 whatsapp_api_type)
            VALUES
                (gen_random_uuid(), :company_id, false, false,
                 true, '22:00', '08:00', 'UNOFFICIAL_BAILEYS')
            ON CONFLICT (company_id) DO NOTHING
        """), {"company_id": str(company_id)})

        # Templates — idempotente via UNIQUE (company_id, event_type, channel, audience)
        for tmpl in _DEFAULT_TEMPLATES:
            conn.execute(sa.text("""
                INSERT INTO communication_templates
                    (template_id, company_id, event_type, channel, audience,
                     body_template, is_active, is_default)
                VALUES
                    (gen_random_uuid(), :company_id, :event_type, :channel,
                     :audience, :body_template, true, true)
                ON CONFLICT (company_id, event_type, channel, audience) DO NOTHING
            """), {
                "company_id": str(company_id),
                "event_type": tmpl["event_type"],
                "channel": tmpl["channel"],
                "audience": tmpl["audience"],
                "body_template": tmpl["body_template"],
            })


def downgrade() -> None:
    # Downgrade não remove dados de tenants — apenas registra
    pass
