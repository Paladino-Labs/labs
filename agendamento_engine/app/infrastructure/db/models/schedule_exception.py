import uuid
from sqlalchemy import Column, String, Date, Time, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ScheduleException(Base):
    __tablename__ = "schedule_exceptions"

    exception_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    exception_date = Column(Date, nullable=False)
    type = Column(String(20), nullable=False)  # SUBSTITUTIVE | ADDITIVE
    start_time = Column(Time, nullable=True)   # NULL = dia todo de folga (SUBSTITUTIVE)
    end_time = Column(Time, nullable=True)
    reason = Column(String(500), nullable=True)

    __table_args__ = (
        UniqueConstraint("professional_id", "exception_date", "type", name="uq_exception_per_day_type"),
    )
