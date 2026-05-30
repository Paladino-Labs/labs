import uuid

import sqlalchemy as sa
from sqlalchemy import Column, Boolean, ForeignKey, Enum as SAEnum, Time
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class CommunicationSetting(Base):
    __tablename__ = "communication_settings"

    settings_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        unique=True,
        nullable=False,
        index=True,
    )

    whatsapp_enabled = Column(Boolean, nullable=False, default=False)
    whatsapp_credential_id = Column(
        UUID(as_uuid=True),
        ForeignKey("integration_credentials.credential_id"),
        nullable=True,
    )
    whatsapp_api_type = Column(
        SAEnum(
            "UNOFFICIAL_BAILEYS",
            "OFFICIAL_META",
            name="whatsappapitype",
            create_type=False,
        ),
        nullable=False,
        default="UNOFFICIAL_BAILEYS",
    )

    email_enabled = Column(Boolean, nullable=False, default=False)
    smtp_credential_id = Column(
        UUID(as_uuid=True),
        ForeignKey("integration_credentials.credential_id"),
        nullable=True,
    )

    quiet_hours_enabled = Column(Boolean, nullable=False, default=True)
    quiet_hours_start = Column(Time, nullable=False, server_default="'22:00'")
    quiet_hours_end = Column(Time, nullable=False, server_default="'08:00'")

    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
