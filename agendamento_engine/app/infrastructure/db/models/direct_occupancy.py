import uuid
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class DirectOccupancy(Base):
    __tablename__ = "direct_occupancies"

    occupancy_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    reason = Column(String(500), nullable=False)
    opened_at = Column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)
    closed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    opened_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
