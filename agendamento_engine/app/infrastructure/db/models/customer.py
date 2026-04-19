import uuid
from sqlalchemy import Column, String, ForeignKey, Boolean, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Customer(Base, TimestampMixin):
    """
    Cliente da barbearia (quem agenda).
    Tabela renomeada de 'clients' para 'customers' na migration f3a9e1d72b04.
    """
    __tablename__ = "customers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)        # observações internas (visível apenas no painel)
    active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", back_populates="customers")
    appointments = relationship("Appointment", back_populates="customer", lazy="dynamic")
