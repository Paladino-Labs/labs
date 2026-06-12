"""
ConsentService — Sprint A. APPEND-ONLY: grant/revoke sempre criam um novo
ConsentRecord; o status vigente é o do registro mais recente.

Defaults quando NENHUM registro existe (padrão da visão):
  COMMUNICATION (transacional) → True  (opt-out, não opt-in)
  MARKETING                    → False (nunca enviar sem GRANTED explícito)
  demais (DATA_PROCESSING, PAYMENT_STORAGE) → False
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models import ConsentRecord

logger = logging.getLogger(__name__)


class ConsentType:
    COMMUNICATION = "COMMUNICATION"
    DATA_PROCESSING = "DATA_PROCESSING"
    PAYMENT_STORAGE = "PAYMENT_STORAGE"
    MARKETING = "MARKETING"

    ALL = (COMMUNICATION, DATA_PROCESSING, PAYMENT_STORAGE, MARKETING)


class ConsentStatus:
    GRANTED = "GRANTED"
    REVOKED = "REVOKED"


class SourceChannel:
    LINK = "LINK"
    BOT = "BOT"
    PORTAL = "PORTAL"
    PAINEL = "PAINEL"


# Consents que valem True quando não há nenhum registro (opt-out)
_DEFAULT_GRANTED_TYPES = {ConsentType.COMMUNICATION}


def _append_record(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
    consent_type: str,
    channel: Optional[str],
    status: str,
    source_channel: str,
    notes: Optional[str] = None,
) -> ConsentRecord:
    record = ConsentRecord(
        identity_id=identity_id,
        company_id=company_id,
        consent_type=consent_type,
        channel=channel,
        status=status,
        source_channel=source_channel,
        notes=notes,
    )
    db.add(record)
    db.commit()
    return record


def grant_consent(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
    consent_type: str,
    channel: Optional[str],
    source_channel: str,
    notes: Optional[str] = None,
) -> ConsentRecord:
    """Append-only: cria novo registro GRANTED."""
    return _append_record(
        db, identity_id, company_id, consent_type, channel,
        ConsentStatus.GRANTED, source_channel, notes,
    )


def revoke_consent(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
    consent_type: str,
    channel: Optional[str],
    source_channel: str,
    notes: Optional[str] = None,
) -> ConsentRecord:
    """Append-only: cria novo registro REVOKED."""
    return _append_record(
        db, identity_id, company_id, consent_type, channel,
        ConsentStatus.REVOKED, source_channel, notes,
    )


def _matching_records(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
    consent_type: Optional[str] = None,
) -> list[ConsentRecord]:
    """
    Registros da identity aplicáveis ao tenant: company_id igual OU NULL
    (consent global Paladino-wide). Filtro fino feito em Python — volume
    por identity é pequeno e a função fica testável com mocks.
    """
    query = db.query(ConsentRecord).filter(ConsentRecord.identity_id == identity_id)
    if consent_type is not None:
        query = query.filter(ConsentRecord.consent_type == consent_type)
    records = query.all()
    return [
        r for r in records
        if r.company_id is None or company_id is None or r.company_id == company_id
    ]


def check_consent(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
    consent_type: str,
    channel: Optional[str],
) -> bool:
    """
    True se o consent mais recente aplicável é GRANTED.

    Registro com channel NULL vale para todos os canais; registro com
    channel específico só vale para aquele canal. Sem nenhum registro:
    COMMUNICATION → True (opt-out) · MARKETING e demais → False.
    """
    records = [
        r for r in _matching_records(db, identity_id, company_id, consent_type)
        if r.channel is None or channel is None or r.channel == channel
    ]
    if not records:
        return consent_type in _DEFAULT_GRANTED_TYPES

    latest = max(records, key=lambda r: r.occurred_at)
    return latest.status == ConsentStatus.GRANTED


def get_consents_for_identity(
    db: Session,
    identity_id: UUID,
    company_id: Optional[UUID],
) -> list[ConsentRecord]:
    """Último registro por (consent_type, channel) — estado vigente."""
    records = _matching_records(db, identity_id, company_id)
    latest_by_key: dict[tuple, ConsentRecord] = {}
    for r in sorted(records, key=lambda r: r.occurred_at):
        latest_by_key[(r.consent_type, r.channel)] = r
    return list(latest_by_key.values())
