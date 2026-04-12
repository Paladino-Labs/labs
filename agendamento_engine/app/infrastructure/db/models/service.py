import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Service(Base, TimestampMixin):
    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    duration = Column(Integer, nullable=False)  # minutos
    active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", back_populates="services")
    professionals = relationship("ProfessionalService", back_populates="service", lazy="dynamic")


class ProfessionalService(Base):
    """Vínculo entre profissional e serviço, com comissão opcional."""
    __tablename__ = "professional_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    commission_percentage = Column(Numeric(5, 2), nullable=True)

    professional = relationship("Professional", back_populates="services")
    service = relationship("Service", back_populates="professionals")
