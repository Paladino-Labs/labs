"""
Controle de idempotência de consumers de eventos.

Convenção obrigatória de key: "{event_type}:{uuid}[:{discriminador}]"
Ex: "booking_session.expired:550e8400-e29b-41d4-a716-446655440000"
    "appointment.reminder_due:550e8400-...:24h"

is_processed e mark_processed devem ser chamados dentro da mesma transação
atômica que processa o evento — garantia de exatamente-uma-execução.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session


def is_processed(key: str, consumer: str, db: Session) -> bool:
    """Retorna True se o par (key, consumer) já foi processado."""
    from sqlalchemy import text
    result = db.execute(
        text(
            "SELECT 1 FROM processed_idempotency_keys "
            "WHERE key = :key AND consumer = :consumer"
        ),
        {"key": key, "consumer": consumer},
    ).first()
    return result is not None


def mark_processed(
    key: str,
    consumer: str,
    event_id: UUID,
    db: Session,
    company_id: UUID | None = None,
    result_summary: str | None = None,
) -> None:
    """
    Registra que o par (key, consumer) foi processado.
    Deve ser chamado dentro da mesma transação do processamento — o caller
    faz db.commit() após ambas as operações.
    """
    from sqlalchemy import text
    db.execute(
        text(
            "INSERT INTO processed_idempotency_keys "
            "(key, consumer, company_id, processed_at, event_id, result_summary) "
            "VALUES (:key, :consumer, :company_id, :processed_at, :event_id, :result_summary) "
            "ON CONFLICT (key, consumer) DO NOTHING"
        ),
        {
            "key": key,
            "consumer": consumer,
            "company_id": company_id,
            "processed_at": datetime.now(timezone.utc),
            "event_id": event_id,
            "result_summary": result_summary,
        },
    )
