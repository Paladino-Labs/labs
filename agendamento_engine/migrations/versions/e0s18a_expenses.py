"""expenses

Revision ID: e0s18a_expenses
Revises: m5n6o7p8q9r0
Create Date: 2026-06-11

Sprint 18 — Despesas + recorrência:
  1. Nova tabela expenses (com RLS padrão app.current_company_id)

Notas:
  - supplier_id UUID SEM FK — tabela suppliers não existe ainda;
    Sprint 17 adicionará a FK via ALTER TABLE.
  - recurrence_rule JSONB no próprio registro (sem tabela expense_recurrences);
    parent_expense_id encadeia as instâncias geradas.
  - category VARCHAR validada no service contra EntryCategory (padrão do projeto).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e0s18a_expenses"
down_revision: Union[str, Sequence[str], None] = "m5n6o7p8q9r0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS expenses (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id         UUID NOT NULL REFERENCES companies(id),
            description        VARCHAR(255) NOT NULL,
            amount             NUMERIC(15,2) NOT NULL CHECK (amount > 0),
            category           VARCHAR(50) NOT NULL,
            supplier_id        UUID,
            due_date           DATE NOT NULL,
            status             VARCHAR(20) NOT NULL DEFAULT 'PENDENTE',
            paid_at            TIMESTAMPTZ,
            paid_amount        NUMERIC(15,2),
            recurrence_rule    JSONB,
            parent_expense_id  UUID REFERENCES expenses(id),
            created_by         UUID NOT NULL REFERENCES users(id),
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_company_id ON expenses (company_id)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_company_status_due "
        "ON expenses (company_id, status, due_date)"
    ))
    op.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_expenses_parent ON expenses (parent_expense_id)"
    ))

    op.execute(sa.text("ALTER TABLE expenses ENABLE ROW LEVEL SECURITY"))
    op.execute(sa.text("""
        CREATE POLICY tenant_isolation ON expenses
          USING (
            company_id::text = current_setting('app.current_company_id', true)
            OR current_setting('app.current_company_id', true) = ''
          )
    """))


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS expenses"))
