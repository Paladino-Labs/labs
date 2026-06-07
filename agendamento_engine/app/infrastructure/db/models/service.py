import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Integer, Numeric, Text
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
    description = Column(Text, nullable=True)
    image_url = Column(String(500), nullable=True)
    active = Column(Boolean, default=True, nullable=False)

    preparation_minutes_before = Column(Integer, nullable=False, default=0, server_default="0")
    preparation_minutes_after  = Column(Integer, nullable=False, default=0, server_default="0")

    company = relationship("Company", back_populates="services")
    professionals = relationship("ProfessionalService", back_populates="service", lazy="dynamic")
    variants = relationship("ServiceVariant", back_populates="service", lazy="dynamic")
    pricing_overrides = relationship("ServicePricingOverride", back_populates="service", lazy="dynamic")


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


class ServicePricingOverride(Base, TimestampMixin):
    """Preço e/ou duração personalizada por profissional+serviço."""
    __tablename__ = "service_pricing_overrides"

    override_id     = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id      = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    service_id      = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    price           = Column(Numeric(10, 2), nullable=False)
    duration_min    = Column(Integer, nullable=True)  # NULL = usa duração do serviço base
    is_active       = Column(Boolean, nullable=False, default=True)

    service      = relationship("Service", back_populates="pricing_overrides")
    professional = relationship("Professional")


class ServiceVariant(Base, TimestampMixin):
    """Variante de serviço com preço e duração próprios (ex: Corte simples, Corte + barba)."""
    __tablename__ = "service_variants"

    variant_id  = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id  = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    service_id  = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    name        = Column(String(255), nullable=False)
    price       = Column(Numeric(10, 2), nullable=False)
    duration_min = Column(Integer, nullable=False)
    is_active   = Column(Boolean, nullable=False, default=True)
    sort_order  = Column(Integer, nullable=False, default=0)

    service = relationship("Service", back_populates="variants")
