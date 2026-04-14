"""remove_availability_slots_table

Revision ID: c9f2e7a14b38
Revises: b7c3d1e9f2a5
Create Date: 2026-04-14

Remove the availability_slots ghost table.
The table was designed as an on-demand cache but was never written to.
Real availability is calculated on-demand from working_hours + appointments +
schedule_blocks by app/modules/availability/service.py.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c9f2e7a14b38'
down_revision: Union[str, Sequence[str], None] = 'b7c3d1e9f2a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("uq_availability_slot", table_name="availability_slots")
    op.drop_table("availability_slots")


def downgrade() -> None:
    op.create_table(
        "availability_slots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professional_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("end_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="AVAILABLE"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["professional_id"], ["professionals.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_availability_slot",
        "availability_slots",
        ["company_id", "professional_id", "start_at"],
        unique=True,
    )
