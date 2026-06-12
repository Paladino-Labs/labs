import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean, CheckConstraint, Column, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class NpsConfig(Base):
    """Configuração de NPS por tenant — Sprint G (1:1 com companies)."""
    __tablename__ = "nps_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, unique=True,
    )
    enabled = Column(Boolean, nullable=False, default=True)
    channel = Column(String(20), nullable=False, default="WHATSAPP")
    delay_minutes = Column(Integer, nullable=False, default=30)
    min_interval_days = Column(Integer, nullable=False, default=30)
    low_score_threshold = Column(Integer, nullable=False, default=6)
    low_score_alert_enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
    )
    updated_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
        onupdate=sa.func.now(),
    )


class NpsSurvey(Base):
    """Pesquisa NPS enviada ao cliente — Sprint G.

    Lifecycle: PENDING → SENT → RESPONDED | EXPIRED
    UNIQUE(appointment_id): no máximo 1 survey por atendimento (idempotência).
    """
    __tablename__ = "nps_surveys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    appointment_id = Column(
        UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False,
    )
    status = Column(String(20), nullable=False, default="PENDING")
    scheduled_for = Column(sa.TIMESTAMP(timezone=True), nullable=False)
    sent_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    responded_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
    expires_at = Column(sa.TIMESTAMP(timezone=True), nullable=False)
    communication_log_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
    )

    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_nps_surveys_appointment"),
    )


class NpsResponse(Base):
    """Resposta do cliente à pesquisa NPS — Sprint G.

    Quase-append-only: tenant só adiciona tenant_response, nunca edita
    score/comment (enforced no service layer).
    """
    __tablename__ = "nps_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    survey_id = Column(
        UUID(as_uuid=True), ForeignKey("nps_surveys.id"),
        nullable=False, unique=True,
    )
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    score = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    tenant_response = Column(Text, nullable=True)
    responded_at = Column(
        sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"),
    )

    __table_args__ = (
        CheckConstraint("score >= 0 AND score <= 10", name="check_nps_score_range"),
    )
