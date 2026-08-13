import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.infrastructure.db.base import Base


class BotMessageLabel(Base):
    """Rótulo humano sobre uma mensagem do bot — S-painel-telemetria.

    O Silva lê a conversa e marca, por mensagem do cliente, o que o bot
    DEVERIA ter entendido. Sem isso a leitura produz impressão; com isso,
    produz o insumo do redesenho do catálogo de intenções.

    ⚠️ 1:1 com `bot_message_traces` (UNIQUE em trace_id) e **CASCADE**: o
    rótulo tem a mesma vida útil de 30 dias do trace que rotula. Rótulo órfão
    não é analisável — perde o texto, o estado e a classificação que o
    justificavam. Ver a migration e0s36 para o racional completo.

    ⚠️ Tabela de PLATAFORMA: sem `company_id`, sem RLS. O tenant da mensagem
    continua sendo lido do trace.

    ⚠️ `expected_intent` é string livre no banco de propósito — o catálogo de
    rótulos é o que este trabalho vai redesenhar. A validação vive na API
    (`platform/telemetry_service.EXPECTED_INTENTS`), onde muda sem migration.
    """
    __tablename__ = "bot_message_labels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("bot_message_traces.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )

    # YES | NO | WRONG — "o bot entendeu?" (CHECK no banco)
    understood = Column(String(10), nullable=True)
    # "o que era?" — ver aviso acima sobre validação na API
    expected_intent = Column(String(40), nullable=True)
    note = Column(Text, nullable=True)

    labeled_by = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
