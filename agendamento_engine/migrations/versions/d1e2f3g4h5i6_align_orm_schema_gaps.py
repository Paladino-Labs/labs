"""align_orm_schema_gaps

Revision ID: d1e2f3g4h5i6
Revises: c2d3e4f5g6h7
Create Date: 2026-06-01

Alinha ORM ↔ banco:
  1. professionals.specialty  — coluna presente no ORM, ausente no banco
  2. products.stock            — coluna presente no ORM, ausente no banco
  3. working_hours constraints — UniqueConstraint removido do ORM; drop no banco
"""

from alembic import op
import sqlalchemy as sa

revision = "d1e2f3g4h5i6"
down_revision = "c2d3e4f5g6h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE professionals
          ADD COLUMN IF NOT EXISTS specialty VARCHAR(255)
    """)

    op.execute("""
        ALTER TABLE products
          ADD COLUMN IF NOT EXISTS stock INTEGER DEFAULT 0
    """)

    op.execute("""
        ALTER TABLE working_hours
          DROP CONSTRAINT IF EXISTS uq_working_hours_day
    """)

    op.execute("""
        ALTER TABLE working_hours
          DROP CONSTRAINT IF EXISTS working_hours_company_id_professional_id_weekday_key
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE working_hours
          ADD CONSTRAINT uq_working_hours_day
          UNIQUE (company_id, professional_id, weekday)
    """)

    op.execute("""
        ALTER TABLE products
          DROP COLUMN IF EXISTS stock
    """)

    op.execute("""
        ALTER TABLE professionals
          DROP COLUMN IF EXISTS specialty
    """)
