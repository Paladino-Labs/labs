"""fix: tenant_isolation policy em appointment_status_log

Revision ID: 22bfd8bf16b3
Revises: h1i2j3k4l5m6
Create Date: 2026-05-28 17:18:05.657715

Adiciona RLS em appointment_status_log, omitida na migration principal.
DROP POLICY IF EXISTS garante idempotência caso a policy já exista.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "22bfd8bf16b3"
down_revision: Union[str, Sequence[str], None] = "h1i2j3k4l5m6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(text("SET LOCAL row_security = off"))
    op.execute(text("ALTER TABLE appointment_status_log ENABLE ROW LEVEL SECURITY"))
    op.execute(text("DROP POLICY IF EXISTS tenant_isolation ON appointment_status_log"))
    op.execute(text("""
        CREATE POLICY tenant_isolation ON appointment_status_log
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(text("DROP POLICY IF EXISTS tenant_isolation ON appointment_status_log"))
    op.execute(text("ALTER TABLE appointment_status_log DISABLE ROW LEVEL SECURITY"))
