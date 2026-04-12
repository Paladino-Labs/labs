import uuid
from sqlalchemy import Column, String, ForeignKey, Index, UniqueConstraint
from sqlalchemy import TIMESTAMP, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.infrastructure.db.base import Base


class BotSession(Base):
    """
    Sessão de conversa do bot WhatsApp.
    Uma linha por usuário (whatsapp_id) por empresa.

    Campos críticos:
      - state          : estado atual da máquina de estados (ex: INICIO, ESCOLHENDO_SERVICO)
      - context        : dados parciais da conversa (JSONB) — service_id, professional_id, etc.
      - last_message_id: ID da última mensagem processada (idempotência de webhook)
      - expires_at     : TTL da sessão; sessões expiradas são limpas por worker
    """
    __tablename__ = "bot_sessions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id"),
        nullable=False,
    )
    # Número E.164 do cliente no WhatsApp (ex: "5511999999999")
    whatsapp_id = Column(String(30), nullable=False)

    state = Column(String(50), nullable=False, default="INICIO", server_default="INICIO")

    # Dados acumulados durante a conversa (service_id, professional_id, slot, etc.)
    context = Column(JSONB(astext_type=String()), nullable=True)

    # Última mensagem processada — previne reprocessamento de re-entregas do webhook
    last_message_id = Column(String(100), nullable=True)

    # TTL da sessão — resetado a cada mensagem, limpeza via worker
    expires_at = Column(TIMESTAMP(timezone=True), nullable=True)

    created_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at = Column(
        TIMESTAMP(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )

    company = relationship("Company")

    __table_args__ = (
        # Uma sessão por cliente por empresa
        UniqueConstraint("company_id", "whatsapp_id", name="uq_bot_sessions_company_whatsapp"),
    )
