import uuid
from sqlalchemy import Column, String, Text, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.infrastructure.db.base import Base


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id         = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
                        nullable=False, unique=True)

    # Identidade
    tagline     = Column(String(180), nullable=True)
    description = Column(Text,        nullable=True)
    logo_url    = Column(String(500), nullable=True)
    cover_url   = Column(String(500), nullable=True)

    # Galeria
    gallery_urls = Column(ARRAY(String(500)), nullable=True, default=list)

    # Contato e localização
    address  = Column(String(255), nullable=True)
    city     = Column(String(100), nullable=True)
    whatsapp = Column(String(30),  nullable=True)
    maps_url = Column(String(500), nullable=True)

    # Redes sociais
    instagram_url = Column(String(255), nullable=True)
    facebook_url  = Column(String(255), nullable=True)
    tiktok_url    = Column(String(255), nullable=True)

    # Avaliações
    google_review_url = Column(String(500), nullable=True)

    # Horário de funcionamento
    business_hours = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    company = relationship("Company", backref="profile", uselist=False)