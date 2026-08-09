import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class BotMessageTrace(Base):
    """Trajetória de UMA mensagem inbound do bot — S-bot-1.

    Uma linha por evento recebido no webhook da Evolution, com o que aconteceu
    em cada etapa: webhook → classificador → dispatcher → saída.

    ⚠️ Instrumento descartável, com retenção de 30 dias
    (`BOT_TRACE_RETENTION_DAYS`, expurgo oportunista em `whatsapp/trace.py`).
    Existe para o redesenho do catálogo de intenções ser feito com dados.

    `company_id` é NULLABLE de propósito: eventos descartados ANTES da
    resolução do tenant (instância desconhecida, JSON inválido, grupo) também
    precisam aparecer — são justamente os que hoje somem sem deixar rastro.

    O telefone do cliente NÃO é gravado em claro: `whatsapp_masked` para leitura
    humana, `whatsapp_hash` para agrupar. Ver a análise de privacidade no
    relatório do sprint.
    """
    __tablename__ = "bot_message_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True,
    )
    received_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Envelope do webhook ───────────────────────────────────────────────────
    instance_name = Column(String(200), nullable=True)
    # messages.upsert | messages.update | connection.update | qrcode.updated | …
    event = Column(String(40), nullable=True)
    whatsapp_hash = Column(String(32), nullable=True, index=True)
    whatsapp_masked = Column(String(60), nullable=True)
    message_id = Column(String(255), nullable=True)
    # conversation | reactionMessage | listResponseMessage | audioMessage | …
    message_type = Column(String(60), nullable=True)

    # ── Contexto do bot ───────────────────────────────────────────────────────
    session_id = Column(UUID(as_uuid=True), nullable=True)
    # Estado da FSM na CHEGADA da mensagem — sem isto não se distingue
    # "handler não soube tratar" de "chegou no estado errado".
    fsm_state = Column(String(40), nullable=True)
    fsm_state_after = Column(String(40), nullable=True)
    # trace.OUTCOME_* — PROCESSED | IGNORED_* | REJECTED_* | ERROR
    outcome = Column(String(40), nullable=False)
    user_input = Column(Text, nullable=True)

    # ── Etapas (JSONB — o formato é instrumento, não contrato) ────────────────
    # payload cru saneado: PII e blobs podados, ESTRUTURA preservada
    webhook = Column(JSONB, nullable=False, default=dict)
    # {regex: {...}, llm: {...}, final: {...}, routing: {...}}
    classifier = Column(JSONB, nullable=False, default=dict)
    # {handler: "...", detail: {...}}
    dispatch = Column(JSONB, nullable=False, default=dict)
    # [{kind, text, ok}, …] — o que o bot respondeu
    outbound = Column(JSONB, nullable=False, default=list)

    duration_ms = Column(Integer, nullable=True)
