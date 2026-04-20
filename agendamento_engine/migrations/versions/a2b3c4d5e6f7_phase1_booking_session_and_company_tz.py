"""Fase 1: BookingSession unificado + company.timezone

Revision ID: a2b3c4d5e6f7
Revises: f5g6h7i8j9k0
Create Date: 2026-04-20

Mudanças:
  1. companies.timezone — fuso horário da empresa (backfill: America/Sao_Paulo)
  2. booking_sessions   — tabela de sessão unificada (todos os canais)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "a2b3c4d5e6f7"
down_revision = "f5g6h7i8j9k0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── 1. companies.timezone ───────────────────────────────────────────────
    # ADD COLUMN com server_default — aplica "America/Sao_Paulo" a todas as
    # linhas existentes sem precisar de UPDATE separado.
    op.add_column(
        "companies",
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="America/Sao_Paulo",
        ),
    )

    # ─── 2. booking_sessions ─────────────────────────────────────────────────
    op.create_table(
        "booking_sessions",

        # Identidade
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),

        # Multi-tenant
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
        ),

        # Canal: "web" | "whatsapp" | "admin"
        sa.Column("channel", sa.String(20), nullable=False),

        # Estado FSM
        sa.Column("state", sa.String(50), nullable=False, server_default="IDLE"),

        # Contexto acumulado (snapshot para UX — não é source of truth)
        sa.Column(
            "context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),

        # Cliente identificado (preenchido em SET_CUSTOMER)
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Agendamento criado (preenchido após CONFIRM bem-sucedido)
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
            nullable=True,
        ),

        # Token para retomada via URL (/book/{slug}?t={token})
        sa.Column("token", sa.String(64), nullable=True, unique=True),

        # Snapshot do timezone da empresa no momento da criação
        sa.Column(
            "company_timezone",
            sa.String(50),
            nullable=False,
            server_default="America/Sao_Paulo",
        ),

        # Controle de idempotência e auditoria
        sa.Column("last_action",    sa.String(50),              nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),

        # TTL — resetado a cada ação bem-sucedida; worker de limpeza usa este campo
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),

        # Timestamps padrão (TimestampMixin equivalente)
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    # ─── Índices ─────────────────────────────────────────────────────────────

    # Listagem de sessões por empresa + canal (ex: sessões web ativas)
    op.create_index(
        "ix_booking_sessions_company_channel",
        "booking_sessions",
        ["company_id", "channel"],
    )

    # Worker de limpeza: DELETE WHERE expires_at < NOW() LIMIT N
    op.create_index(
        "ix_booking_sessions_expires_at",
        "booking_sessions",
        ["expires_at"],
    )

    # Busca por token (retomada de sessão web)
    op.create_index(
        "ix_booking_sessions_token",
        "booking_sessions",
        ["token"],
        unique=True,
        postgresql_where=sa.text("token IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_booking_sessions_token",          table_name="booking_sessions")
    op.drop_index("ix_booking_sessions_expires_at",     table_name="booking_sessions")
    op.drop_index("ix_booking_sessions_company_channel", table_name="booking_sessions")
    op.drop_table("booking_sessions")
    op.drop_column("companies", "timezone")
