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
