import uuid
from sqlalchemy import Column, ForeignKey, Numeric, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class CompanySettings(Base):
    __tablename__ = "company_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        unique=True,
    )
    default_commission_percentage = Column(Numeric(5, 2), nullable=False, default=40.00)
    slot_interval_minutes = Column(Integer, nullable=False, default=15)
    max_advance_booking_days = Column(Integer, nullable=False, default=60)
    require_payment_upfront = Column(Boolean, nullable=False, default=False)
    # Bot WhatsApp — ativo/inativo por empresa (default desligado)
    bot_enabled = Column(Boolean, nullable=False, default=False, server_default="false")

    company = relationship("Company")
