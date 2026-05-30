import uuid

import sqlalchemy as sa
from sqlalchemy import Column, String, Text, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class CommunicationLog(Base):
    __tablename__ = "communication_logs"

    log_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    template_id = Column(
        UUID(as_uuid=True),
        ForeignKey("communication_templates.template_id"),
        nullable=True,
    )
    event_type = Column(String(100), nullable=False)
    channel = Column(
        SAEnum("WHATSAPP", "EMAIL", "SMS", name="communicationchannel", create_type=False),
        nullable=False,
    )
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_type = Column(
        SAEnum("CLIENT", "PROFESSIONAL", "OWNER", name="communicationaudience", create_type=False),
        nullable=False,
    )
    status = Column(
        SAEnum(
            "SENT",
            "FAILED",
            "SKIPPED_QUIET_HOURS",
            "SKIPPED_NO_CONSENT",
            "SKIPPED_CHANNEL_DISABLED",
            "SKIPPED_NO_TEMPLATE",
            "SCHEDULED",
            name="communicationlogstatus",
            create_type=False,
        ),
        nullable=False,
    )
    # Preenchido quando mensagem cai em quiet_hours e deve ser entregue depois.
    scheduled_send_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    rendered_body = Column(Text, nullable=True)
    sent_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
