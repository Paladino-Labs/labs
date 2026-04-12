import uuid
from sqlalchemy import Column, String, Boolean, ForeignKey, Time, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy import TIMESTAMP

from app.infrastructure.db.base import Base, TimestampMixin


class WorkingHour(Base):
    """Horário de trabalho semanal de um profissional."""
    __tablename__ = "working_hours"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=seg ... 6=dom
    opening_time = Column(Time, nullable=False)
    closing_time = Column(Time, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    professional = relationship("Professional", back_populates="working_hours")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "professional_id", "weekday",
            name="uq_working_hours_day",
        ),
    )


class ScheduleBlock(Base, TimestampMixin):
    """
    Bloqueio manual de horário — ex: férias, folga, evento.
    Substitui 'blocked_slots' do código legado.
    """
    __tablename__ = "schedule_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    reason = Column(String(255), nullable=True)


class AvailabilitySlot(Base, TimestampMixin):
    """
    Cache operacional de disponibilidade.
    Nunca é a fonte de verdade — appointments é.
    Status: AVAILABLE | BOOKED | BLOCKED
    """
    __tablename__ = "availability_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    status = Column(String(20), nullable=False, default="AVAILABLE")

    __table_args__ = (
        UniqueConstraint(
            "company_id", "professional_id", "start_at",
            name="uq_availability_slot",
        ),
    )
