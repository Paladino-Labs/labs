"""commission_fee_policy v2 — BARBERSHOP_PAYS / SPLIT_50_50 / BARBER_PAYS

Revision ID: k3l4m5n6o7p8
Revises: j2k3l4m5n6o7
Create Date: 2026-06-08
"""
from alembic import op

revision: str = "k3l4m5n6o7p8"
down_revision: str = "j2k3l4m5n6o7"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        UPDATE commission_policies
        SET commission_fee_policy = 'BARBERSHOP_PAYS'
        WHERE commission_fee_policy = 'BEFORE_FEES'
    """)
    op.execute("""
        UPDATE commission_policies
        SET commission_fee_policy = 'SPLIT_50_50'
        WHERE commission_fee_policy = 'AFTER_FEES'
    """)


def downgrade():
    op.execute("""
        UPDATE commission_policies
        SET commission_fee_policy = 'BEFORE_FEES'
        WHERE commission_fee_policy = 'BARBERSHOP_PAYS'
    """)
    op.execute("""
        UPDATE commission_policies
        SET commission_fee_policy = 'AFTER_FEES'
        WHERE commission_fee_policy = 'SPLIT_50_50'
    """)
    # BARBER_PAYS não tem equivalente semântico — fallback conservador
    op.execute("""
        UPDATE commission_policies
        SET commission_fee_policy = 'BEFORE_FEES'
        WHERE commission_fee_policy = 'BARBER_PAYS'
    """)
