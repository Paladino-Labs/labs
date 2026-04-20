"""create web_booking_sessions table

Revision ID: f5g6h7i8j9k0
Revises: e3c8b5d91a47
Create Date: 2026-04-19

Tracks completed online bookings made via the public booking link.
Each record corresponds to one confirmed appointment created through
the /public/{slug}/book endpoint.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f5g6h7i8j9k0"
down_revision = "e3c8b5d91a47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_booking_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("companies.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "appointment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("appointments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("customer_name", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(30), nullable=True),
        # source: 'web' | 'whatsapp_link'
        sa.Column("source", sa.String(20), nullable=False, server_default="web"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("ix_web_booking_sessions_token", "web_booking_sessions", ["token"])


def downgrade() -> None:
    op.drop_index("ix_web_booking_sessions_token", table_name="web_booking_sessions")
    op.drop_table("web_booking_sessions")
