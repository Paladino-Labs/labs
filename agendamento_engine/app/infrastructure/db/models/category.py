import uuid
import enum

from sqlalchemy import Column, String, Boolean, Integer, ForeignKey, Enum as SAEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class EntityType(str, enum.Enum):
    SERVICE = "SERVICE"
    PRODUCT = "PRODUCT"
    EXPENSE = "EXPENSE"


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("company_id", "name", "entity_type", name="uq_category_company_name_type"),
    )

    category_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    entity_type = Column(
        SAEnum("SERVICE", "PRODUCT", "EXPENSE", name="entitytype", create_type=False),
        nullable=False,
    )
    is_default = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    sort_order = Column(Integer, nullable=False, default=0)
