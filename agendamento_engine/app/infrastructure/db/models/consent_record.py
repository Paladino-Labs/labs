import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ConsentRecord(Base):
    """
    Registro de consentimento LGPD — Sprint A. APPEND-ONLY: nunca UPDATE
    ou DELETE (trigger consent_records_no_update no banco). Revogação é
    um novo registro com status=REVOKED.

    company_id NULL = consent global Paladino-wide.
    RLS habilitado sem policy (padrão paladino_identities) — acesso
    exclusivamente via service layer (identity/consent_service.py).
    """
    __tablename__ = "consent_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identity_id = Column(
        UUID(as_uuid=True), ForeignKey("paladino_identities.id"), nullable=False
    )
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    # COMMUNICATION | DATA_PROCESSING | PAYMENT_STORAGE | MARKETING
    consent_type = Column(String(30), nullable=False)
    # WHATSAPP | EMAIL | SMS — NULL para consentimentos gerais (todos os canais)
    channel = Column(String(20), nullable=True)
    # GRANTED | REVOKED
    status = Column(String(10), nullable=False)
    # LINK | BOT | PORTAL | PAINEL
    source_channel = Column(String(20), nullable=False)
    occurred_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    notes = Column(Text, nullable=True)
