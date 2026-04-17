"""add online_booking_enabled to company_settings

Revision ID: a1b2c3d4e5f6
Revises: 
Create Date: 2026-04-17

Adiciona campo online_booking_enabled em company_settings.
Default False — nenhuma empresa expõe agendamento online sem ativar explicitamente.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "a1b2c3d4e5f6"
down_revision = None  # substituir pelo revision_id da migration anterior
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "company_settings",
        sa.Column(
            "online_booking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("company_settings", "online_booking_enabled")