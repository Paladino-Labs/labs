"""sprint2_user_invitations_audit_logs

Cria as tabelas user_invitations e audit_logs.

audit_logs é append-only enforced via triggers no banco:
  - audit_no_update: bloqueia UPDATE
  - audit_no_delete: bloqueia DELETE

Revision ID: b3c4d5e6f7a8
Revises: b2c3d4e5f6a7
Create Date: 2026-05-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    bind = op.get_bind()

    # ── Criar enum invitationstatus ──────────────────────────────────────────
    invitation_status = postgresql.ENUM(
        "PENDING",
        "ACCEPTED",
        "EXPIRED",
        "CANCELLED",
        name="invitationstatus",
    )
    invitation_status.create(bind, checkfirst=True)

    # ── Referência ao enum já existente userrole ─────────────────────────────
    # IMPORTANTE: NÃO criar novamente
    userrole_enum = postgresql.ENUM(
        "OWNER",
        "ADMIN",
        "OPERATOR",
        "PROFESSIONAL",
        "CLIENT",
        "PLATFORM_OWNER",
        "PLATFORM_SUPPORT",
        "PLATFORM_BILLING",
        "PLATFORM_READONLY",
        name="userrole",
        create_type=False,
    )

    # ── Referência ao enum invitationstatus já criado acima ─────────────────
    invitation_status_enum = postgresql.ENUM(
        "PENDING",
        "ACCEPTED",
        "EXPIRED",
        "CANCELLED",
        name="invitationstatus",
        create_type=False,
    )

    # ── Tabela user_invitations ──────────────────────────────────────────────
    op.create_table(
        "user_invitations",

        sa.Column(
            "invitation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=True,
        ),

        sa.Column(
            "email",
            sa.String(255),
            nullable=False,
        ),

        sa.Column(
            "role",
            userrole_enum,
            nullable=False,
        ),

        sa.Column(
            "token",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "expires_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now() + interval '48 hours'"),
        ),

        sa.Column(
            "status",
            invitation_status_enum,
            nullable=False,
            server_default=sa.text("'PENDING'::invitationstatus"),
        ),

        sa.Column(
            "invited_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index(
        "ix_user_invitations_email",
        "user_invitations",
        ["email"],
    )

    op.create_index(
        "ix_user_invitations_company_id",
        "user_invitations",
        ["company_id"],
    )

    # ── Tabela audit_logs ────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",

        sa.Column(
            "audit_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),

        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),

        sa.Column(
            "actor_role",
            sa.String(50),
            nullable=False,
        ),

        sa.Column(
            "action",
            sa.String(100),
            nullable=False,
        ),

        sa.Column(
            "resource_type",
            sa.String(100),
            nullable=False,
        ),

        sa.Column(
            "resource_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),

        sa.Column(
            "amount",
            sa.Numeric(15, 2),
            nullable=True,
        ),

        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),

        sa.Column(
            "reason",
            sa.Text,
            nullable=True,
        ),

        sa.Column(
            "correlation_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),

        sa.Column(
            "before_snapshot",
            postgresql.JSONB,
            nullable=True,
        ),

        sa.Column(
            "after_snapshot",
            postgresql.JSONB,
            nullable=True,
        ),

        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.Column(
            "ip_address",
            sa.String(45),
            nullable=True,
        ),

        sa.Column(
            "user_agent",
            sa.Text,
            nullable=True,
        ),
    )

    op.create_index(
        "ix_audit_logs_company_id",
        "audit_logs",
        ["company_id"],
    )

    op.create_index(
        "ix_audit_logs_actor_id",
        "audit_logs",
        ["actor_id"],
    )

    op.create_index(
        "ix_audit_logs_occurred_at",
        "audit_logs",
        ["occurred_at"],
    )

    op.create_index(
        "ix_audit_logs_action",
        "audit_logs",
        ["action"],
    )

    # ── Triggers append-only ────────────────────────────────────────────────
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_modification()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs é append-only: % não é permitido', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_no_update
          BEFORE UPDATE ON audit_logs
          FOR EACH ROW
          EXECUTE FUNCTION prevent_audit_modification();
    """)

    op.execute("""
        CREATE TRIGGER audit_no_delete
          BEFORE DELETE ON audit_logs
          FOR EACH ROW
          EXECUTE FUNCTION prevent_audit_modification();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_no_delete ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_no_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_modification()")

    op.drop_table("audit_logs")
    op.drop_table("user_invitations")

    postgresql.ENUM(
        name="invitationstatus"
    ).drop(op.get_bind(), checkfirst=True)
