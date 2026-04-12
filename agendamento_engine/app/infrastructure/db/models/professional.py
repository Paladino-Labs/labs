import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Professional(Base, TimestampMixin):
    __tablename__ = "professionals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", back_populates="professionals")
    services = relationship("ProfessionalService", back_populates="professional", lazy="dynamic")
    appointments = relationship("Appointment", back_populates="professional", lazy="dynamic")
    working_hours = relationship("WorkingHour", back_populates="professional", lazy="dynamic")
