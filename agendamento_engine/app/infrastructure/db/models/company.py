import uuid
from sqlalchemy import Column, String, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Company(Base, TimestampMixin):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=True, unique=True)
    active = Column(Boolean, default=True, nullable=False)

    users = relationship("User", back_populates="company", lazy="dynamic")
    professionals = relationship("Professional", back_populates="company", lazy="dynamic")
    services = relationship("Service", back_populates="company", lazy="dynamic")
    customers = relationship("Customer", back_populates="company", lazy="dynamic")
    products = relationship("Product", back_populates="company", lazy="dynamic")
