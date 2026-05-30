import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, Boolean, ForeignKey
from sqlalchemy import VARCHAR
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy as sa

from app.infrastructure.db.base import Base


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    token_hash = Column(VARCHAR(255), nullable=False, unique=True)
    expires_at = Column(sa.TIMESTAMP(timezone=True), nullable=False)
    used = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
