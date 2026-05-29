"""rls: add policies to remaining 4 tables

Revision ID: i1j2k3l4m5n6
Revises: 22bfd8bf16b3
Create Date: 2026-05-28

Tabelas com company_id direto (política padrão):
  professional_services, schedule_blocks, working_hours

Tabela sem company_id (JOIN):
  appointment_services — snapshot de serviço; company_id vive em appointments.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "i1j2k3l4m5n6"
down_revision: Union[str, Sequence[str], None] = "22bfd8bf16b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STANDARD_TABLES = [
    "professional_services",
    "schedule_blocks",
    "working_hours",
]


def upgrade() -> None:
    op.execute(text("SET LOCAL row_security = off"))

    # ── Tabelas com company_id — política padrão ──────────────────────────────
    for table in _STANDARD_TABLES:
        op.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
        op.execute(text(f"""
            CREATE POLICY tenant_isolation ON {table}
              USING (
                company_id::text = current_setting('app.current_company_id', true)
                OR current_setting('app.current_company_id', true) = ''
              )
        """))

    # ── appointment_services: sem company_id — JOIN em appointments ───────────
    op.execute(text("ALTER TABLE appointment_services ENABLE ROW LEVEL SECURITY"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON appointment_services
          USING (
            EXISTS (
              SELECT 1 FROM appointments a
              WHERE a.id = appointment_services.appointment_id
              AND (
                a.company_id::text = current_setting('app.current_company_id', true)
                OR current_setting('app.current_company_id', true) = ''
              )
            )
          )
    """))


def downgrade() -> None:
    all_tables = _STANDARD_TABLES + ["appointment_services"]
    for table in all_tables:
        op.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
        op.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
