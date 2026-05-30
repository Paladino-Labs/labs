import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, Enum as SAEnum, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


def _now_utc():
    return datetime.now(timezone.utc)


class InvitationStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class UserInvitation(Base):
    __tablename__ = "user_invitations"

    invitation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    email = Column(String(255), nullable=False, index=True)
    role = Column(
        SAEnum(
            "OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT",
            "PLATFORM_OWNER", "PLATFORM_SUPPORT", "PLATFORM_BILLING",
            "PLATFORM_READONLY",
            name="userrole",
            create_type=False,
        ),
        nullable=False,
    )
    token = Column(UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=False)
    status = Column(
        SAEnum(
            "PENDING", "ACCEPTED", "EXPIRED", "CANCELLED",
            name="invitationstatus",
            create_type=False,
        ),
        nullable=False,
        default="PENDING",
    )
    invited_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
    )
    created_at = Column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=_now_utc,
    )
