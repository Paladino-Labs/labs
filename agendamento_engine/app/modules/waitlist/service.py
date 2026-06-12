"""
WaitlistService — Sprint G.

Fila de espera orientada a eventos, com escopo SERVICE | PROFESSIONAL | PRODUCT:
  - Entrada via painel ou bot; duplicata no mesmo escopo → 409
  - Cliente com operação ativa equivalente (appointment SCHEDULED/IN_PROGRESS
    no mesmo escopo) → 422 no join e PULADO na notificação (regra da visão)
  - notify_waitlist: consome appointment.cancelled / appointment.rescheduled /
    stock.entry_recorded; notifica APENAS o 1º candidato elegível —
    notificação não reserva o slot (primeiro a agir leva)
  - Ordem: priority DESC, created_at ASC (FIFO puro quando priority=0)
  - Entry NOTIFIED expira após notification_window_hours → próximo da fila
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import (
    Appointment, AppointmentService, Customer, WaitlistConfig, WaitlistEntry,
)
from app.infrastructure.event_bus import DomainEvent, event_bus

logger = logging.getLogger(__name__)

_ACTIVE_APPOINTMENT_STATUSES = ("SCHEDULED", "IN_PROGRESS")

# Status de dispatch considerados "notificação entregue ao fluxo"
_DISPATCH_OK = {"SENT", "SCHEDULED"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _publish(event_type: str, company_id: UUID, idempotency_key: str, payload: dict) -> None:
    """Publica evento best-effort — falha nunca derruba o fluxo."""
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=_now(),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": None},
            payload=payload,
        ))
    except Exception:
        logger.exception("waitlist: falha ao publicar %s", event_type)


def get_or_create_config(db: Session, company_id: UUID) -> WaitlistConfig:
    config = db.query(WaitlistConfig).filter(WaitlistConfig.company_id == company_id).first()
    if config is None:
        config = WaitlistConfig(company_id=company_id)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def _validate_scope(
    scope_type: str,
    service_id: Optional[UUID],
    professional_id: Optional[UUID],
    product_id: Optional[UUID],
) -> None:
    expected = {
        "SERVICE": service_id,
        "PROFESSIONAL": professional_id,
        "PRODUCT": product_id,
    }
    if scope_type not in expected:
        raise HTTPException(status_code=422, detail=f"scope_type inválido: {scope_type}")
    if expected[scope_type] is None:
        raise HTTPException(
            status_code=422,
            detail=f"Escopo {scope_type} exige o id correspondente",
        )
    others = [v for k, v in expected.items() if k != scope_type]
    if any(v is not None for v in others):
        raise HTTPException(
            status_code=422,
            detail="Apenas o id do escopo selecionado deve ser preenchido",
        )


def has_active_equivalent_operation(
    db: Session,
    company_id: UUID,
    customer_id: UUID,
    scope_type: str,
    service_id: Optional[UUID] = None,
    professional_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
) -> bool:
    """Cliente já tem appointment SCHEDULED/IN_PROGRESS no mesmo escopo?

    PRODUCT não tem operação equivalente no Estágio 0 (compra não é
    agendável) → sempre False.
    """
    if scope_type == "PRODUCT":
        return False

    query = db.query(Appointment).filter(
        Appointment.company_id == company_id,
        Appointment.client_id == customer_id,
        Appointment.status.in_(_ACTIVE_APPOINTMENT_STATUSES),
    )
    if scope_type == "PROFESSIONAL":
        query = query.filter(Appointment.professional_id == professional_id)
    elif scope_type == "SERVICE":
        query = query.join(
            AppointmentService,
            AppointmentService.appointment_id == Appointment.id,
        ).filter(AppointmentService.service_id == service_id)

    return query.first() is not None


def join_waitlist(
    db: Session,
    company_id: UUID,
    customer_id: UUID,
    scope_type: str,
    service_id: Optional[UUID] = None,
    professional_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    source_channel: str = "PAINEL",
) -> WaitlistEntry:
    config = get_or_create_config(db, company_id)
    if config.enabled is not True:
        raise HTTPException(status_code=422, detail="Fila de espera desabilitada para esta empresa")

    _validate_scope(scope_type, service_id, professional_id, product_id)

    duplicate = (
        db.query(WaitlistEntry)
        .filter(
            WaitlistEntry.company_id == company_id,
            WaitlistEntry.customer_id == customer_id,
            WaitlistEntry.scope_type == scope_type,
            WaitlistEntry.service_id == service_id,
            WaitlistEntry.professional_id == professional_id,
            WaitlistEntry.product_id == product_id,
            WaitlistEntry.status.in_(("WAITING", "NOTIFIED")),
        )
        .first()
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="Cliente já está na fila para este escopo")

    if has_active_equivalent_operation(
        db, company_id, customer_id, scope_type,
        service_id=service_id, professional_id=professional_id, product_id=product_id,
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Cliente já possui um agendamento ativo equivalente — "
                "não é necessário entrar na fila de espera"
            ),
        )

    entry = WaitlistEntry(
        company_id=company_id,
        customer_id=customer_id,
        scope_type=scope_type,
        service_id=service_id,
        professional_id=professional_id,
        product_id=product_id,
        status="WAITING",
        source_channel=source_channel,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)

    _publish(
        "waitlist.entry_created", company_id,
        f"waitlist.entry_created:{entry.id}",
        {
            "entry_id": str(entry.id),
            "customer_id": str(customer_id),
            "company_id": str(company_id),
            "scope_type": scope_type,
        },
    )
    return entry


def cancel_entry(db: Session, company_id: UUID, entry_id: UUID) -> WaitlistEntry:
    entry = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.id == entry_id, WaitlistEntry.company_id == company_id)
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Entrada não encontrada")
    if entry.status not in ("WAITING", "NOTIFIED"):
        raise HTTPException(status_code=422, detail=f"Entrada já está em estado {entry.status}")
    entry.status = "CANCELLED"
    db.commit()
    db.refresh(entry)
    return entry


def notify_waitlist(
    db: Session,
    company_id: UUID,
    scope_type: str,
    service_id: Optional[UUID] = None,
    professional_id: Optional[UUID] = None,
    product_id: Optional[UUID] = None,
    reason: str = "slot_released",
) -> Optional[WaitlistEntry]:
    """Notifica o 1º candidato elegível da fila para o escopo. Retorna a entry
    notificada ou None quando ninguém é elegível."""
    from app.modules.communication.service import communication_service

    config = db.query(WaitlistConfig).filter(WaitlistConfig.company_id == company_id).first()
    if config is not None and config.enabled is not True:
        return None
    window_hours = config.notification_window_hours if config else 2

    query = db.query(WaitlistEntry).filter(
        WaitlistEntry.company_id == company_id,
        WaitlistEntry.scope_type == scope_type,
        WaitlistEntry.status == "WAITING",
    )
    if scope_type == "SERVICE":
        query = query.filter(WaitlistEntry.service_id == service_id)
    elif scope_type == "PROFESSIONAL":
        query = query.filter(WaitlistEntry.professional_id == professional_id)
    elif scope_type == "PRODUCT":
        query = query.filter(WaitlistEntry.product_id == product_id)

    candidates = query.order_by(
        WaitlistEntry.priority.desc(), WaitlistEntry.created_at.asc(),
    ).all()

    for entry in candidates:
        # Regra da visão: cliente com operação ativa equivalente é PULADO
        if has_active_equivalent_operation(
            db, company_id, entry.customer_id, scope_type,
            service_id=service_id, professional_id=professional_id, product_id=product_id,
        ):
            continue

        customer = db.query(Customer).filter(Customer.id == entry.customer_id).first()
        if customer is None:
            continue

        try:
            log = communication_service.dispatch(
                event_type="waitlist.slot_available",
                company_id=company_id,
                context={
                    "cliente_nome": customer.name,
                    "recipient_phone": customer.phone,
                    "recipient_email": getattr(customer, "email", None) or "",
                },
                recipient_id=entry.customer_id,
                recipient_type="CLIENT",
                db=db,
            )
        except Exception:
            logger.exception("waitlist: dispatch falhou entry_id=%s", entry.id)
            continue

        # Consent revogado ou skip → próximo candidato
        if log is None or log.status not in _DISPATCH_OK:
            continue

        now = _now()
        entry.status = "NOTIFIED"
        entry.notified_at = now
        entry.expires_at = now + timedelta(hours=window_hours)
        db.commit()
        db.refresh(entry)

        _publish(
            "waitlist.customer_notified", company_id,
            f"waitlist.customer_notified:{entry.id}:{now.isoformat()}",
            {
                "entry_id": str(entry.id),
                "customer_id": str(entry.customer_id),
                "company_id": str(company_id),
                "scope_type": scope_type,
                "reason": reason,
            },
        )
        # Slot é único — apenas o 1º elegível é notificado
        return entry

    return None


def expire_waitlist_entries(db: Session) -> int:
    """Worker: NOTIFIED com expires_at < now() → EXPIRED; notifica o próximo."""
    now = _now()
    stale = (
        db.query(WaitlistEntry)
        .filter(WaitlistEntry.status == "NOTIFIED", WaitlistEntry.expires_at < now)
        .all()
    )
    expired = 0
    for entry in stale:
        entry.status = "EXPIRED"
        db.commit()
        expired += 1
        _publish(
            "waitlist.entry_expired", entry.company_id,
            f"waitlist.entry_expired:{entry.id}",
            {"entry_id": str(entry.id), "company_id": str(entry.company_id)},
        )
        # O slot continua livre — passa a vez ao próximo da fila
        try:
            notify_waitlist(
                db, entry.company_id, entry.scope_type,
                service_id=entry.service_id,
                professional_id=entry.professional_id,
                product_id=entry.product_id,
                reason="previous_entry_expired",
            )
        except Exception:
            logger.exception("waitlist: falha ao notificar próximo após expiração entry_id=%s", entry.id)
    return expired
