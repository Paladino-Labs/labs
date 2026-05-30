"""
EventBus in-process para o Estágio 0.

Handlers são chamados síncronos no mesmo request para eventos tolerantes
(booking_session.expired). Fluxos críticos de appointment NÃO passam pelo
EventBus — são enfileirados diretamente em tasks Celery (ver Sprint 5).

Perda em crash do processo é aceitável para eventos tolerantes no Estágio 0.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class DomainEvent:
    event_id: UUID
    event_type: str
    occurred_at: datetime
    company_id: UUID | None
    idempotency_key: str
    actor: dict          # { type: TENANT_USER|SYSTEM|CLIENT, id: UUID }
    payload: dict


class EventBus:
    def __init__(self) -> None:
        self._handlers: Dict[str, List[Callable[[DomainEvent], None]]] = {}

    def register(self, event_type: str, handler: Callable[[DomainEvent], None]) -> None:
        self._handlers.setdefault(event_type, []).append(handler)
        logger.debug("event_bus: handler registrado event_type=%s handler=%s", event_type, handler.__name__)

    def publish(self, event: DomainEvent) -> None:
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            logger.debug("event_bus: nenhum handler para event_type=%s", event.event_type)
            return
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    "event_bus: handler falhou event_type=%s handler=%s event_id=%s",
                    event.event_type, handler.__name__, event.event_id,
                )


event_bus = EventBus()
