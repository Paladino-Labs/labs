import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Professional(Base, TimestampMixin):
    __tablename__ = "professionals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    specialty = Column(String(255), nullable=True)

    # Sprint 8 — PII criptografado; nunca armazenar plaintext
    cpf_cnpj_encrypted = Column(Text, nullable=True)      # Fernet(PII_ENCRYPTION_KEY)
    cpf_cnpj_hash = Column(Text, nullable=True)           # HMAC-SHA256 para dedup
    cpf_cnpj_masked = Column(String(18), nullable=True)   # "***.***.***-12"
    external_wallet_id = Column(String(255), nullable=True)

    # Sprint 27 — vínculo 1:1 opcional com a conta de login (role=PROFESSIONAL)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )

    company = relationship("Company", back_populates="professionals")
    user = relationship("User", foreign_keys=[user_id])
    services = relationship("ProfessionalService", back_populates="professional", lazy="dynamic")
    appointments = relationship("Appointment", back_populates="professional", lazy="dynamic")
    working_hours = relationship("WorkingHour", back_populates="professional", lazy="dynamic")
