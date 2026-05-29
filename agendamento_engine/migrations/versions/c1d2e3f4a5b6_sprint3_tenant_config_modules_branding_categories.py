"""sprint3_tenant_config_modules_branding_categories

Cria tabelas: tenant_configs, module_activations, tenant_brandings, categories.
Enums novos: accountingmode, modulename, entitytype.
Trigger: block_accrual_mode — bloqueia accounting_mode=ACCRUAL no Estágio 0.

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-05-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ── Enums ────────────────────────────────────────────────────────────────

    postgresql.ENUM(
        "CASH", "ACCRUAL",
        name="accountingmode",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "ESTOQUE", "COMISSOES", "PACOTES", "ASSINATURAS", "PROMOCOES",
        "CRM", "NPS", "FILA", "BOT_WHATSAPP", "LINK_PUBLICO",
        name="modulename",
    ).create(bind, checkfirst=True)

    postgresql.ENUM(
        "SERVICE", "PRODUCT", "EXPENSE",
        name="entitytype",
    ).create(bind, checkfirst=True)

    # Referências sem create_type para uso nas colunas abaixo
    accountingmode = postgresql.ENUM("CASH", "ACCRUAL", name="accountingmode", create_type=False)
    modulename = postgresql.ENUM(
        "ESTOQUE", "COMISSOES", "PACOTES", "ASSINATURAS", "PROMOCOES",
        "CRM", "NPS", "FILA", "BOT_WHATSAPP", "LINK_PUBLICO",
        name="modulename", create_type=False,
    )
    entitytype = postgresql.ENUM("SERVICE", "PRODUCT", "EXPENSE", name="entitytype", create_type=False)

    # ── tenant_configs ───────────────────────────────────────────────────────

    op.create_table(
        "tenant_configs",

        sa.Column(
            "tenant_config_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            unique=True,
            nullable=False,
        ),

        # Operacional
        sa.Column("timezone", sa.String(50), nullable=False, server_default="America/Sao_Paulo"),
        sa.Column("soft_reservation_ttl_min", sa.Integer, nullable=False, server_default="15"),
        sa.Column("draft_expiration_min", sa.Integer, nullable=False, server_default="60"),
        sa.Column("requested_expiration_h", sa.Integer, nullable=False, server_default="24"),
        sa.Column("no_show_threshold_min", sa.Integer, nullable=False, server_default="30"),
        sa.Column("no_penalty_cancel_h", sa.Integer, nullable=False, server_default="12"),
        sa.Column("require_payment_upfront", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "default_commission_pct",
            sa.Numeric(5, 2),
            nullable=False,
            server_default="40.00",
        ),

        # Placeholder FK — tenant_fee_routing_policies criada na Fase 2 Sprint 6
        sa.Column("fee_routing_policy_id", postgresql.UUID(as_uuid=True), nullable=True),

        # Contábil
        sa.Column(
            "accounting_mode",
            accountingmode,
            nullable=False,
            server_default=sa.text("'CASH'::accountingmode"),
        ),

        # RBAC opt-ins
        sa.Column(
            "permission_overrides",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_index("ix_tenant_configs_company_id", "tenant_configs", ["company_id"])

    # Trigger que bloqueia accounting_mode = ACCRUAL no Estágio 0
    op.execute("""
        CREATE OR REPLACE FUNCTION block_accrual_mode()
        RETURNS trigger AS $$
        BEGIN
            IF NEW.accounting_mode = 'ACCRUAL' THEN
                RAISE EXCEPTION 'accounting_mode ACCRUAL indisponível no Estágio 0';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER enforce_cash_mode
            BEFORE INSERT OR UPDATE ON tenant_configs
            FOR EACH ROW EXECUTE FUNCTION block_accrual_mode();
    """)

    # ── module_activations ───────────────────────────────────────────────────

    op.create_table(
        "module_activations",

        sa.Column(
            "activation_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),

        sa.Column("module_name", modulename, nullable=False),

        sa.Column("is_active", sa.Boolean, nullable=False, server_default="false"),

        sa.Column("activated_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.TIMESTAMP(timezone=True), nullable=True),

        sa.Column(
            "activated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),

        sa.UniqueConstraint("company_id", "module_name", name="uq_module_activation"),
    )

    op.create_index("ix_module_activations_company_id", "module_activations", ["company_id"])

    # ── tenant_brandings ─────────────────────────────────────────────────────

    op.create_table(
        "tenant_brandings",

        sa.Column(
            "branding_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            unique=True,
            nullable=False,
        ),

        sa.Column("logo_url", sa.String, nullable=True),
        sa.Column("primary_color", sa.String(7), nullable=True),
        sa.Column("secondary_color", sa.String(7), nullable=True),
        sa.Column("font_family", sa.String, nullable=True),
        sa.Column("favicon_url", sa.String, nullable=True),

        sa.Column(
            "custom_texts",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    op.create_index("ix_tenant_brandings_company_id", "tenant_brandings", ["company_id"])

    # ── categories ───────────────────────────────────────────────────────────

    op.create_table(
        "categories",

        sa.Column(
            "category_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),

        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id"),
            nullable=False,
        ),

        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("entity_type", entitytype, nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),

        sa.UniqueConstraint(
            "company_id", "name", "entity_type",
            name="uq_category_company_name_type",
        ),
    )

    op.create_index("ix_categories_company_id", "categories", ["company_id"])


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS enforce_cash_mode ON tenant_configs")
    op.execute("DROP FUNCTION IF EXISTS block_accrual_mode()")

    op.drop_table("categories")
    op.drop_table("tenant_brandings")
    op.drop_table("module_activations")
    op.drop_table("tenant_configs")

    bind = op.get_bind()
    postgresql.ENUM(name="entitytype").drop(bind, checkfirst=True)
    postgresql.ENUM(name="modulename").drop(bind, checkfirst=True)
    postgresql.ENUM(name="accountingmode").drop(bind, checkfirst=True)
