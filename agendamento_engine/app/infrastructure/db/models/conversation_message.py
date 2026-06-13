import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class ConversationMessage(Base):
    """Mensagem persistida de uma conversa do bot — Sprint 2.7.

    Persistida enquanto a sessão está em atendimento humano (state=HUMANO),
    dando ao atendente o histórico para responder pelo painel.

    direction: INBOUND (cliente→sistema) | OUTBOUND (sistema→cliente)
    sender_type: CLIENT | BOT | AGENT (atendente humano)
    """
    __tablename__ = "conversation_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    session_id = Column(
        UUID(as_uuid=True), ForeignKey("bot_sessions.id"),
        nullable=False, index=True,
    )
    direction = Column(String(10), nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(20), nullable=False, default="TEXT")
    sender_type = Column(String(20), nullable=False)
    # preenchido quando sender_type=AGENT
    agent_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # ID da mensagem no WhatsApp (para deduplicação)
    whatsapp_message_id = Column(String(100), nullable=True)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
