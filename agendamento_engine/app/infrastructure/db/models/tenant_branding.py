import uuid

import sqlalchemy as sa
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.infrastructure.db.base import Base


class TenantBranding(Base):
    __tablename__ = "tenant_brandings"

    branding_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    logo_url = Column(String, nullable=True)
    primary_color = Column(String(7), nullable=True)
    secondary_color = Column(String(7), nullable=True)
    font_family = Column(String, nullable=True)
    favicon_url = Column(String, nullable=True)
    custom_texts = Column(JSONB, nullable=False, default=dict)
    updated_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
