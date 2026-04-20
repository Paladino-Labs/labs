import uuid
import secrets
from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base, TimestampMixin


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


class WebBookingSession(Base, TimestampMixin):
    """
    Registro de agendamento feito via link público (/book/{slug}).

    Criado atomicamente junto com o Appointment no endpoint
    POST /public/{slug}/book. Serve para rastreamento de origem
    (web vs. WhatsApp), analytics e como identificador único da
    sessão de agendamento online (token na URL de confirmação).
    """
    __tablename__ = "web_booking_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Token público — enviado ao frontend para a URL de confirmação
    token = Column(String(64), nullable=False, unique=True, default=_gen_token, index=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False, index=True)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey("appointments.id", ondelete="SET NULL"), nullable=True)
    customer_name = Column(String(255), nullable=True)
    customer_phone = Column(String(30), nullable=True)
    # 'web' ou 'whatsapp_link' (futuro)
    source = Column(String(20), nullable=False, default="web")

    appointment = relationship("Appointment", foreign_keys=[appointment_id])
