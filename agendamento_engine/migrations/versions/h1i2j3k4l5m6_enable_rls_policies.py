"""enable_rls_policies: Row Level Security em todas as tabelas multi-tenant

Revision ID: h1i2j3k4l5m6
Revises: g1h2i3j4k5l6
Create Date: 2026-05-28

Habilita RLS + política tenant_isolation nas tabelas com company_id.
Estratégia: lê app.current_company_id (setado pelo checkout listener SQLAlchemy).
  - valor preenchido  → filtra ao tenant correspondente
  - string vazia ('')  → PLATFORM_OWNER / worker de plataforma → acesso irrestrito

Tabelas com tratamento especial:
  companies            — política baseada em id (não company_id)
  users                — company_id nullable (PLATFORM_OWNER tem NULL)
  audit_logs           — company_id nullable (ações de plataforma)
  processed_idempotency_keys — company_id nullable (eventos de plataforma)
  password_reset_tokens — sem company_id; política por JOIN em users

Tabela availability_slots: REMOVIDA em migration anterior (c9f2e7a14b38) — ignorada.
Tabelas working_hours e schedule_blocks: têm company_id mas não estavam no escopo original.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "h1i2j3k4l5m6"
down_revision: Union[str, Sequence[str], None] = "g1h2i3j4k5l6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Política padrão: company_id NOT NULL e igual ao contexto, OU bypass (string vazia)
_STANDARD_TABLES = [
    "appointments",
    "booking_sessions",
    "bot_sessions",
    "company_profiles",
    "company_settings",
    "customers",
    "products",
    "professionals",
    "services",
    "web_booking_sessions",
    "whatsapp_connections",
    "user_invitations",
    "tenant_configs",
    "module_activations",
    "tenant_brandings",
    "categories",
    "integration_credentials",
    "communication_settings",
    "communication_templates",
    "communication_logs",
]


def upgrade() -> None:
    # Migrations rodam como superuser no Supabase — BYPASSRLS automático.
    # SET LOCAL para segurança em ambientes onde o role não tem BYPASSRLS.
    op.execute(text("SET LOCAL row_security = off"))

    # ── Tabelas padrão ────────────────────────────────────────────────────────
    for table in _STANDARD_TABLES:
        op.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(text(f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (
                company_id::text = current_setting('app.current_company_id', true)
                OR current_setting('app.current_company_id', true) = ''
              )
        """))

    # ── companies: política por id (a própria empresa deve ser visível) ───────
    op.execute(text("ALTER TABLE companies ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON companies
          USING (
            id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))

    # ── users: company_id nullable (PLATFORM_OWNER tem NULL) ──────────────────
    op.execute(text("ALTER TABLE users ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON users
          USING (
            (company_id IS NOT NULL
             AND company_id::text = current_setting('app.current_company_id', true))
            OR company_id IS NULL
            OR current_setting('app.current_company_id', true) = ''
          )
    """))

    # ── audit_logs: company_id nullable (ações de plataforma sem tenant) ──────
    op.execute(text("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON audit_logs
          USING (
            (company_id IS NOT NULL
             AND company_id::text = current_setting('app.current_company_id', true))
            OR company_id IS NULL
            OR current_setting('app.current_company_id', true) = ''
          )
    """))

    # ── processed_idempotency_keys: company_id nullable (eventos de plataforma)
    op.execute(text("ALTER TABLE processed_idempotency_keys ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON processed_idempotency_keys
          USING (
            (company_id IS NOT NULL
             AND company_id::text = current_setting('app.current_company_id', true))
            OR company_id IS NULL
            OR current_setting('app.current_company_id', true) = ''
          )
    """))

    # ── password_reset_tokens: sem company_id — JOIN em users ─────────────────
    op.execute(text("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON password_reset_tokens
          USING (
            EXISTS (
              SELECT 1 FROM users u
              WHERE u.id = password_reset_tokens.user_id
              AND (
                (u.company_id IS NOT NULL
                 AND u.company_id::text = current_setting('app.current_company_id', true))
                OR u.company_id IS NULL
                OR current_setting('app.current_company_id', true) = ''
              )
            )
          )
    """))


def downgrade() -> None:
    op.execute(text("SET LOCAL row_security = off"))

    all_tables = _STANDARD_TABLES + [
        "companies",
        "users",
        "audit_logs",
        "processed_idempotency_keys",
        "password_reset_tokens",
    ]
    for table in all_tables:
        op.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
