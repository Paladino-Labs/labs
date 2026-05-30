import uuid

from sqlalchemy import Column, String, Text, Boolean, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class CommunicationTemplate(Base):
    __tablename__ = "communication_templates"
    __table_args__ = (
        UniqueConstraint(
            "company_id", "event_type", "channel", "audience",
            name="uq_communication_template",
        ),
    )

    template_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    event_type = Column(String(100), nullable=False)
    channel = Column(
        SAEnum("WHATSAPP", "EMAIL", "SMS", name="communicationchannel", create_type=False),
        nullable=False,
    )
    audience = Column(
        SAEnum("CLIENT", "PROFESSIONAL", "OWNER", name="communicationaudience", create_type=False),
        nullable=False,
    )
    body_template = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
