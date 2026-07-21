import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class BotInboundMessage(Base):
    """Buffer durável de mensagens recebidas do webhook do bot WhatsApp — S2.1.

    O webhook persiste a mensagem crua ANTES de responder 200 e enfileira o
    processamento no worker (drain_bot_inbound). Serve a dois propósitos:
      - durabilidade: se o worker cair após o 200, a linha continua RECEIVED e
        o sweeper do beat a re-enfileira (nada se perde);
      - ordenação: é a fila por conversa (company_id + whatsapp_id) que o drain
        consome em ordem de chegada.

    status: RECEIVED (aguardando drain) | PROCESSING (drain em andamento)
            | DONE (processada) | FAILED (esgotou retries → dead-letter)
    """
    __tablename__ = "bot_inbound_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    instance_name = Column(String(100), nullable=False)
    # JID completo do remetente — chave da conversa junto com company_id
    whatsapp_id = Column(String(100), nullable=False)
    # ID da mensagem no WhatsApp — dedup durável (UNIQUE por company)
    whatsapp_message_id = Column(String(100), nullable=False)
    # Payload cru do evento (data já desembrulhado do batch) — o worker o
    # processa idêntico ao caminho síncrono de hoje.
    raw_payload = Column(JSONB, nullable=False)
    # RECEIVED | PROCESSING | DONE | FAILED
    status = Column(String(20), nullable=False, default="RECEIVED", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    processed_at = Column(sa.TIMESTAMP(timezone=True), nullable=True)
