import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import Column, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.infrastructure.db.base import Base


class IntentClassification(Base):
    """Log auditável de classificações do IntentClassifier — Sprint 2.0.

    Append-only: toda classificação (REGEX | LLM | FALLBACK) é persistida
    (invariante 3), sem dedup.
    """
    __tablename__ = "intent_classifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    session_id = Column(UUID(as_uuid=True), nullable=True)
    raw_input = Column(Text, nullable=False)
    classified_intent = Column(String(50), nullable=False)
    # 0.000 a 1.000
    confidence = Column(Numeric(4, 3), nullable=False)
    # REGEX | LLM | FALLBACK
    source = Column(String(10), nullable=False)
    entities = Column(JSONB, nullable=False, default=dict)
    # NULL para REGEX/FALLBACK
    llm_provider = Column(String(30), nullable=True)
    llm_model = Column(String(50), nullable=True)
    llm_latency_ms = Column(Integer, nullable=True)
    classified_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # ── Contexto (F5a) — tornam a telemetria autossuficiente ──────────────────
    # Estado FSM no momento da classificação (INICIO | MENU_PRINCIPAL)
    fsm_state = Column(String(40), nullable=True)
    # Decisão de roteamento efetivamente tomada (telemetry.ROUTING_*):
    # ROUTED | MENU_FALLBACK | SHADOW_NOT_ROUTED | INACTIVE_MODULE_MSG.
    # Escrita no MESMO request da classificação (não é mutação posterior).
    routing_decision = Column(String(30), nullable=True)


class IntentOutcome(Base):
    """Desfecho de uma classificação — o sinal do volante de telemetria (F5a).

    Tabela-irmã 1:1 (UNIQUE classification_id) para preservar o modelo
    append-only de intent_classifications: o desfecho chega em request
    POSTERIOR à classificação e vira INSERT aqui, nunca UPDATE lá.
    Classificação SEM linha aqui = desfecho PENDING (LEFT JOIN na análise).
    """
    __tablename__ = "intent_outcomes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(
        UUID(as_uuid=True), ForeignKey("companies.id"),
        nullable=False, index=True,
    )
    classification_id = Column(
        UUID(as_uuid=True),
        ForeignKey("intent_classifications.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )
    # MENU_CLICK_AFTER_FALLBACK | FLOW_CONFIRMED | FLOW_CANCELLED | ABANDONED
    outcome = Column(String(40), nullable=False)
    # ex.: {"menu_option": "opt_agendar"} | {"appointment_id": "..."} | {"reason": "superseded"}
    outcome_detail = Column(JSONB, nullable=False, default=dict)
    outcome_at = Column(
        sa.TIMESTAMP(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
