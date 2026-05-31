import uuid
from sqlalchemy import Column, String, ForeignKey, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class Reservation(Base):
    __tablename__ = "reservations"

    reservation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    type = Column(String(10), nullable=False)          # SOFT | FIRME (imutável)
    status = Column(String(20), nullable=False, default="ACTIVE")
    # ACTIVE | EXPIRED | CANCELLED | PROMOTED | RELEASED | CONSUMED | NO_SHOW
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=True)
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)  # apenas SOFT
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)
