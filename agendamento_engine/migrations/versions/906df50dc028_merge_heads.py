"""merge heads

Revision ID: 906df50dc028
Revises: a1b2c3d4e5f6, c9f2e7a14b38, e1f4a2b3c9d7
Create Date: 2026-04-17 06:50:53.644296

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '906df50dc028'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4e5f6', 'c9f2e7a14b38', 'e1f4a2b3c9d7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
