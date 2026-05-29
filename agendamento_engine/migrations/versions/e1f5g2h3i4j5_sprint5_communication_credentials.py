"""sprint5: integration_credentials, communication_settings, templates, logs

Revision ID: e1f5g2h3i4j5
Revises: d1e2f3a4b5c6
Create Date: 2026-05-27

Cria as 4 tabelas do Sprint 5:
- integration_credentials  — credenciais de integração por tenant (Fernet)
- communication_settings   — configurações de canal por tenant
- communication_templates  — templates de mensagem por tenant
- communication_logs       — log de envios

Também registra os enums PostgreSQL necessários.
Migration idempotente: tolerante a bancos onde as tabelas já existem.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f5g2h3i4j5"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    """Retorna True se a tabela já existe no schema public."""
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :t AND table_schema = 'public'"
    ), {"t": table_name})
    return result.fetchone() is not None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enums (idempotente via checkfirst=True) ───────────────────────────────

    credentialprovider_enum = postgresql.ENUM(
        "WHATSAPP_EVOLUTION", "WHATSAPP_META", "SMTP", "ASAAS",
        name="credentialprovider", create_type=False,
    )
    credentialstatus_enum = postgresql.ENUM(
        "ACTIVE", "REVOKED",
        name="credentialstatus", create_type=False,
    )
    whatsappapitype_enum = postgresql.ENUM(
        "UNOFFICIAL_BAILEYS", "OFFICIAL_META",
        name="whatsappapitype", create_type=False,
    )
    communicationchannel_enum = postgresql.ENUM(
        "WHATSAPP", "EMAIL", "SMS",
        name="communicationchannel", create_type=False,
    )
    communicationaudience_enum = postgresql.ENUM(
        "CLIENT", "PROFESSIONAL", "OWNER",
        name="communicationaudience", create_type=False,
    )
    communicationlogstatus_enum = postgresql.ENUM(
        "SENT", "FAILED", "SKIPPED_QUIET_HOURS", "SKIPPED_NO_CONSENT",
        "SKIPPED_CHANNEL_DISABLED", "SKIPPED_NO_TEMPLATE", "SCHEDULED",
        name="communicationlogstatus", create_type=False,
    )

    credentialprovider_enum.create(bind, checkfirst=True)
    credentialstatus_enum.create(bind, checkfirst=True)
    whatsappapitype_enum.create(bind, checkfirst=True)
    communicationchannel_enum.create(bind, checkfirst=True)
    communicationaudience_enum.create(bind, checkfirst=True)
    communicationlogstatus_enum.create(bind, checkfirst=True)

    # ── integration_credentials ───────────────────────────────────────────────

    if not _table_exists("integration_credentials"):
        op.create_table(
            "integration_credentials",
            sa.Column("credential_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("provider", credentialprovider_enum, nullable=False),
            sa.Column("label", sa.String(100), nullable=True),
            sa.Column("secret_encrypted", sa.Text, nullable=False),
            sa.Column("masked_preview", sa.String(20), nullable=True),
            sa.Column("config", postgresql.JSONB(astext_type=sa.Text()),
                      nullable=False, server_default="{}"),
            sa.Column("status", credentialstatus_enum,
                      nullable=False, server_default="ACTIVE"),
            sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("revoked_by", postgresql.UUID(as_uuid=True), nullable=True),
            sa.PrimaryKeyConstraint("credential_id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
            sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        )

    # ── communication_settings ────────────────────────────────────────────────

    if not _table_exists("communication_settings"):
        op.create_table(
            "communication_settings",
            sa.Column("settings_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("whatsapp_enabled", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("whatsapp_credential_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("whatsapp_api_type", whatsappapitype_enum,
                      nullable=False, server_default="UNOFFICIAL_BAILEYS"),
            sa.Column("email_enabled", sa.Boolean, nullable=False, server_default="false"),
            sa.Column("smtp_credential_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("quiet_hours_enabled", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("quiet_hours_start", sa.Time, nullable=False, server_default="'22:00'"),
            sa.Column("quiet_hours_end", sa.Time, nullable=False, server_default="'08:00'"),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("settings_id"),
            sa.UniqueConstraint("company_id", name="uq_communication_settings_company"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(
                ["whatsapp_credential_id"],
                ["integration_credentials.credential_id"],
            ),
            sa.ForeignKeyConstraint(
                ["smtp_credential_id"],
                ["integration_credentials.credential_id"],
            ),
        )
        op.create_index("ix_communication_settings_company_id",
                        "communication_settings", ["company_id"], unique=False)

    # ── communication_templates ───────────────────────────────────────────────

    if not _table_exists("communication_templates"):
        op.create_table(
            "communication_templates",
            sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("channel", communicationchannel_enum, nullable=False),
            sa.Column("audience", communicationaudience_enum, nullable=False),
            sa.Column("body_template", sa.Text, nullable=False),
            sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
            sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
            sa.PrimaryKeyConstraint("template_id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.UniqueConstraint(
                "company_id", "event_type", "channel", "audience",
                name="uq_communication_template",
            ),
        )
        op.create_index("ix_communication_templates_company_id",
                        "communication_templates", ["company_id"], unique=False)

    # ── communication_logs ────────────────────────────────────────────────────

    if not _table_exists("communication_logs"):
        op.create_table(
            "communication_logs",
            sa.Column("log_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("event_type", sa.String(100), nullable=False),
            sa.Column("channel", communicationchannel_enum, nullable=False),
            sa.Column("recipient_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("recipient_type", communicationaudience_enum, nullable=False),
            sa.Column("status", communicationlogstatus_enum, nullable=False),
            sa.Column("scheduled_send_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("rendered_body", sa.Text, nullable=True),
            sa.Column("sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text, nullable=True),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("log_id"),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
            sa.ForeignKeyConstraint(
                ["template_id"],
                ["communication_templates.template_id"],
            ),
        )
        op.create_index("ix_communication_logs_company_id",
                        "communication_logs", ["company_id"], unique=False)


def downgrade() -> None:
    op.drop_table("communication_logs")
    op.drop_table("communication_templates")
    op.drop_table("communication_settings")
    op.drop_table("integration_credentials")
