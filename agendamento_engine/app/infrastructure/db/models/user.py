import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="ADMIN")  # ADMIN | PROFESSIONAL | CLIENT
    active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", back_populates="users")

    @property
    def name(self) -> str:
        return self.email.split("@")[0].replace(".", " ").title()

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"
