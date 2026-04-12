from sqlalchemy import (
    Column,
    String,
    Numeric,
    ForeignKey,
    TIMESTAMP,
    CheckConstraint,
    UniqueConstraint,
    Integer,
    Time,
    Boolean,
    DateTime,
    Enum
)
from sqlalchemy.dialects.postgresql import UUID
from pydantic import BaseModel
from sqlalchemy.orm import declarative_base, relationship
import uuid

Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)

class Client(Base):
    __tablename__ = "clients"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False, unique=True)
    email = Column(String, nullable=True)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

class Professional(Base):
    __tablename__ = "professionals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    active = Column(Boolean, default=True)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

class Service(Base):
    __tablename__ = "services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    name = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    duration = Column(Integer, nullable=False)

    active = Column(Boolean, default=True)

    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)

class ProfessionalService(Base):
    __tablename__ = "professional_services"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=False)
    commission_percentage = Column(Numeric(5, 2), nullable=True)

class WorkingHour(Base):
    __tablename__ = "working_hours"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)

    weekday = Column(Integer, nullable=False) #0=Segunda, 6=Domingo
    opening_time = Column(Time, nullable=False)
    closing_time = Column(Time, nullable=False)
    is_active = Column(Boolean, default=True)

    __table_args__ = (
        # Garante apenas uma regra de horário por dia para cada profissional
        UniqueConstraint("company_id", "professional_id", "weekday", name="uq_working_hours_day"),
    )

class BlockedSlot(Base):
    __tablename__ = "blocked_slots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    professional_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)
    reason = Column(String(100), nullable=True)

    # Nota: A EXCLUDE CONSTRAINT deve der criada via Migration (Alembic)
    # ou SQL manual, pois o SQLAlchemy não tem suporte nativo completo para GIST.

# --- SPRINT 1: NÚCLEO TRANSACIONAL ---

class Appointment(Base):
    __tablename__ = "appointments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # 1. Padronização: tenant_id por company_id para bater com o escopo
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    professional_id = Column(UUID(as_uuid=True), ForeignKey("professionals.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)

    # 2. Verdade Temporal: TIMESTAMPTZ garantido
    start_at = Column(TIMESTAMP(timezone=True), nullable=False)
    end_at = Column(TIMESTAMP(timezone=True), nullable=False)

    # Verdade Matemática
    # 3. Verdade Matemática: Numéric(10, 2) evita imprecição
    subtotal_amount = Column(Numeric(10, 2), nullable=False)
    discount_amount = Column(Numeric(10, 2), nullable=False, default=0)
    total_amount = Column(Numeric(10, 2), nullable=False)
    total_commission = Column(Numeric(10, 2), nullable=False, default=0)
    financial_status = Column(String, default="pending")

    # Idempotência e Concorrência
    # 4. Idempotência: UNIQUE por empresa (Blindagem contra retry)
    idempotency_key = Column(String, nullable=False)
    version = Column(Integer, default=1, nullable=False) # Optimistic Locking

    status = Column(String, default="SCHEDULED", nullable=False)

    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    client = relationship("Client")
    professional = relationship("Professional")

    services = relationship(
        "AppointmentService",
        backref="appointment",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        CheckConstraint(
            "total_amount = subtotal_amount - discount_amount",
            name="check_math_integrity"
        ),
        UniqueConstraint("company_id", "idempotency_key", name="uq_idempotency"),
    )


class AppointmentService(Base):
    __tablename__ = "appointment_services"

    # PK padronizada para 'id' para evitar confusão com ID do catálogo de serviços
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False)

    service_id = Column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    
    # Snapshot: guarda os valores do momento do agendamento
    service_name = Column(String, nullable=False)
    duration_snapshot = Column(Numeric, nullable=False)
    price_snapshot = Column(Numeric(10, 2), nullable=False)

class AppointmentStatusLog(Base):
    __tablename__ = "appointment_status_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id"), nullable=False)
    from_status = Column(String, nullable=True)
    to_status = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default="now()", nullable=False)

class CompanySettings(Base):
    __tablename__ = "company_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False, unique=True)

    default_commission_percentage = Column(Numeric(5,2), nullable=False, default=40.00)

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), nullable=False)

    email = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)

    is_admin = Column(Boolean, default=True)

class LoginRequest(BaseModel):
    email: str
    password: str

