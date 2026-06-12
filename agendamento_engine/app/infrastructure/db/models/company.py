import uuid
from sqlalchemy import Column, Numeric, String, Boolean
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=True, unique=True)
    active = Column(Boolean, default=True, nullable=False)

    # Sprint C — lifecycle do tenant na plataforma:
    # TRIAL | ACTIVE | SUSPENDED | CHURNED.
    # SUSPENDED bloqueia login dos usuários do tenant (dados preservados).
    status = Column(String(20), nullable=False, default="ACTIVE", server_default="ACTIVE")

    # Fuso horário da empresa (IANA, ex: "America/Sao_Paulo").
    # Obrigatório para geração correta de labels de data/hora e exibição no frontend.
    # Backfill padrão: "America/Sao_Paulo" (aplicado pela migration).
    timezone = Column(String(50), nullable=False, server_default="America/Sao_Paulo")

    # Sprint 8 — Asaas subconta
    payment_provider = Column(String(50), nullable=True)
    external_account_id = Column(String(255), nullable=True)
    external_account_status = Column(String(50), nullable=True)
    external_account_created_at = Column(TIMESTAMP(timezone=True), nullable=True)

    # Ajuste 9 — campos obrigatórios para criação de subconta Asaas
    owner_cpf_cnpj = Column(String(20), nullable=True)
    owner_birth_date = Column(String(10), nullable=True)
    owner_mobile_phone = Column(String(20), nullable=True)
    owner_income_value = Column(Numeric(12, 2), nullable=True)
    owner_address = Column(String(200), nullable=True)
    owner_address_number = Column(String(20), nullable=True)
    owner_province = Column(String(100), nullable=True)
    owner_postal_code = Column(String(10), nullable=True)

    users = relationship("User", back_populates="company", lazy="dynamic")
    professionals = relationship("Professional", back_populates="company", lazy="dynamic")
    services = relationship("Service", back_populates="company", lazy="dynamic")
    customers = relationship("Customer", back_populates="company", lazy="dynamic")
    products = relationship("Product", back_populates="company", lazy="dynamic")
