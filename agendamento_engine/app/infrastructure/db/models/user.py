import uuid
import enum
from sqlalchemy import Column, String, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class UserRole(str, enum.Enum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    PROFESSIONAL = "PROFESSIONAL"
    CLIENT = "CLIENT"
    PLATFORM_OWNER = "PLATFORM_OWNER"
    # [SCHEMA APENAS] — Estágio 1+
    PLATFORM_SUPPORT = "PLATFORM_SUPPORT"
    PLATFORM_BILLING = "PLATFORM_BILLING"
    PLATFORM_READONLY = "PLATFORM_READONLY"


# Papéis reservados — não atribuíveis via API no Estágio 0
SCHEMA_ONLY_ROLES = {
    UserRole.PLATFORM_SUPPORT,
    UserRole.PLATFORM_BILLING,
    UserRole.PLATFORM_READONLY,
}

# Hierarquia de escalonamento: quem pode convidar/atribuir para quê
# OWNER pode convidar qualquer papel ativo; ADMIN só OPERATOR/PROFESSIONAL
INVITE_PERMISSION: dict = {
    "OWNER": {"OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT"},
    "ADMIN": {"OPERATOR", "PROFESSIONAL"},
    "OPERATOR": set(),
    "PROFESSIONAL": set(),
    "CLIENT": set(),
    "PLATFORM_OWNER": {
        "OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT", "PLATFORM_OWNER"
    },
}


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # nullable=True: PLATFORM_OWNER não pertence a um tenant
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=True,
        index=True,
    )
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    role = Column(
        SAEnum(
            "OWNER", "ADMIN", "OPERATOR", "PROFESSIONAL", "CLIENT",
            "PLATFORM_OWNER", "PLATFORM_SUPPORT", "PLATFORM_BILLING",
            "PLATFORM_READONLY",
            name="userrole",
            create_type=False,
        ),
        nullable=False,
        default="ADMIN",
    )
    active = Column(Boolean, default=True, nullable=False)

    company = relationship("Company", back_populates="users")

    @property
    def name(self) -> str:
        return self.email.split("@")[0].replace(".", " ").title()

    @property
    def is_admin(self) -> bool:
        return self.role in ("ADMIN", "OWNER", "PLATFORM_OWNER")
