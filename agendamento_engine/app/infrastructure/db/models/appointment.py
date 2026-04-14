import uuid
import sqlalchemy as sa
from sqlalchemy import (
    Boolean, Column, String, ForeignKey, Numeric, Integer,
    TIMESTAMP, CheckConstraint, UniqueConstraint, DateTime,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


class Appointment(Base, TimestampMixin):
    """
    Aggregate root do sistema de agendamento.
    Nenhum outro módulo altera estados críticos diretamente aqui.
    """
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)

    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Financeiro — calculado pelo backend
    subtotal_amount = Column(Numeric(10, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    total_commission = Column(Numeric(10, 2), nullable=False, default=0)

    # Status operacional: SCHEDULED | IN_PROGRESS | COMPLETED | CANCELLED | NO_SHOW
    status = Column(String(20), nullable=False, default="SCHEDULED")

    # Status financeiro: UNPAID | PAID | REFUNDED
    financial_status = Column(String(20), nullable=False, default="UNPAID")

    idempotency_key = Column(String(255), nullable=False)
    version = Column(Integer, default=1, nullable=False)

    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancel_reason = Column(String(500), nullable=True)

    # Flags de idempotência para workers de lembrete
    reminder_24h_sent = Column(Boolean, nullable=False, server_default=sa.text("FALSE"))
    reminder_2h_sent  = Column(Boolean, nullable=False, server_default=sa.text("FALSE"))

    # Relacionamentos
    professional = relationship("Professional", back_populates="appointments")
    customer = relationship("Customer", back_populates="appointments", foreign_keys=[client_id])
    services = relationship(
        "AppointmentService",
        back_populates="appointment",
        cascade="all, delete-orphan",
    )
    status_logs = relationship(
        "AppointmentStatusLog",
        back_populates="appointment",
        lazy="dynamic",
    )

    __table_args__ = (
        CheckConstraint(
            "total_amount = subtotal_amount - discount_amount",
            name="check_total_math",
        ),
        UniqueConstraint("company_id", "idempotency_key", name="uq_idempotency"),
    )


class AppointmentService(Base):
    """Snapshot imutável do serviço no momento do agendamento."""
    __tablename__ = "appointment_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appointments.id", ondelete="CASCADE"),
        nullable=False,
    )
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    service_name = Column(String(255), nullable=False)
    duration_snapshot = Column(Numeric, nullable=False)      # minutos
    price_snapshot = Column(Numeric(10, 2), nullable=False)  # preço travado

    appointment = relationship("Appointment", back_populates="services")


class AppointmentStatusLog(Base):
    """Auditoria de cada transição de estado do agendamento."""
    __tablename__ = "appointment_status_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=False)
    changed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note = Column(String(500), nullable=True)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)

    appointment = relationship("Appointment", back_populates="status_logs")
