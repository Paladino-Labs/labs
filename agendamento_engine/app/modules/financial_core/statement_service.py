"""StatementService — conciliação com extrato externo (Sprint E).

API pública:
    import_csv       — importa CSV idempotente por SHA-256 da linha
    suggest_match    — candidatos a match (apenas sugestão, zero persistência)
    confirm_match    — vincula entry a Movement (unidirecional — Movement intocado)
    dismiss_entry    — dispensa entry com reason obrigatório
    list_statement_entries, list_batches — queries

Invariantes:
    - Movement NUNCA é alterado (append-only preservado): o vínculo vive
      exclusivamente em ExternalStatementEntry.matched_movement_id.
    - Re-upload do mesmo CSV não duplica: UNIQUE (company_id, line_hash).
    - auto_matched no import conta entries com candidato encontrado —
      nada é persistido como MATCHED automaticamente (confirmação é manual).
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import uuid as uuid_mod
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.infrastructure.db.models.external_statement_entry import ExternalStatementEntry
from app.infrastructure.db.models.movement import Movement
from app.infrastructure.event_bus import event_bus, DomainEvent

logger = logging.getLogger(__name__)

# Tolerância de arredondamento no match de valores
_AMOUNT_TOLERANCE = Decimal("0.01")
# Janela de datas do match: occurred_at ±2 dias
_MATCH_WINDOW_DAYS = 2

_OUTFLOW_TOKENS = {"OUTFLOW", "D", "DEBIT", "DEBITO", "SAIDA"}
_INFLOW_TOKENS = {"INFLOW", "C", "CREDIT", "CREDITO", "ENTRADA"}


def _publish(event_type: str, company_id, idempotency_key: str, payload: dict) -> None:
    """Publica evento best-effort — falha nunca propaga."""
    try:
        event_bus.publish(DomainEvent(
            event_id=uuid_mod.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": str(company_id)},
            payload=payload,
        ))
    except Exception:
        logger.exception("statement: falha ao publicar %s", event_type)


# ── parsing do CSV ────────────────────────────────────────────────────────────

def _line_hash(raw_line: str) -> str:
    return hashlib.sha256(raw_line.strip().encode("utf-8")).hexdigest()


def _parse_date(value: str) -> Optional[date]:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _parse_amount(value: str) -> Optional[Decimal]:
    """Aceita formatos BR ("1.234,56", "-150,00") e internacional ("-1234.56")."""
    cleaned = value.strip().replace("R$", "").replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        # O separador mais à direita é o decimal
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _cell(row: list[str], header: Optional[list[str]], key) -> Optional[str]:
    """Resolve coluna por índice (int) ou por nome (str, requer header)."""
    if key is None:
        return None
    if isinstance(key, int) or (isinstance(key, str) and key.lstrip("-").isdigit()):
        idx = int(key)
        return row[idx] if 0 <= idx < len(row) else None
    if header is None:
        return None
    try:
        return row[header.index(key)]
    except (ValueError, IndexError):
        return None


def _infer_direction(direction_cell: Optional[str], amount: Decimal) -> str:
    if direction_cell:
        token = direction_cell.strip().upper()
        if token in _OUTFLOW_TOKENS:
            return "OUTFLOW"
        if token in _INFLOW_TOKENS:
            return "INFLOW"
    return "OUTFLOW" if amount < 0 else "INFLOW"


# ── queries internas ──────────────────────────────────────────────────────────

def _get_entry(entry_id: UUID, company_id: UUID, db: Session) -> ExternalStatementEntry:
    entry = (
        db.query(ExternalStatementEntry)
        .filter(
            ExternalStatementEntry.id == entry_id,
            ExternalStatementEntry.company_id == company_id,
        )
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Lançamento de extrato não encontrado")
    return entry


def _matched_movement_ids(company_id: UUID, db: Session) -> set:
    """IDs de Movements já casados com alguma entry do tenant."""
    rows = (
        db.query(ExternalStatementEntry.matched_movement_id)
        .filter(
            ExternalStatementEntry.company_id == company_id,
            ExternalStatementEntry.matched_movement_id.isnot(None),
        )
        .all()
    )
    return {row[0] for row in rows}


def _find_candidates(
    entry_account_id: UUID,
    entry_amount: Decimal,
    entry_direction: str,
    entry_date: date,
    company_id: UUID,
    db: Session,
    exclude_movement_ids: Optional[set] = None,
) -> list[Movement]:
    """Candidatos a match: mesmo account, |amount| igual (±0.01), data ±2 dias,
    direção compatível, Movement não casado. Ordenados por proximidade de data."""
    window_start = datetime.combine(
        entry_date - timedelta(days=_MATCH_WINDOW_DAYS), time.min, tzinfo=timezone.utc
    )
    window_end = datetime.combine(
        entry_date + timedelta(days=_MATCH_WINDOW_DAYS), time.max, tzinfo=timezone.utc
    )

    movement_types = (
        {"INFLOW", "TRANSFER_IN"} if entry_direction == "INFLOW"
        else {"OUTFLOW", "TRANSFER_OUT"}
    )
    target = abs(entry_amount)

    # SQL restringe ao tenant/conta/janela; os critérios são revalidados em
    # Python (defesa em profundidade — e única camada exercitada nos testes
    # com Session mockada, padrão do projeto).
    rows = (
        db.query(Movement)
        .filter(
            Movement.company_id == company_id,
            Movement.account_id == entry_account_id,
            Movement.occurred_at >= window_start,
            Movement.occurred_at <= window_end,
        )
        .all()
    )

    taken = exclude_movement_ids
    if taken is None:
        taken = _matched_movement_ids(company_id, db)

    def _as_utc(dt: datetime) -> datetime:
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    candidates = []
    for m in rows:
        if m.account_id != entry_account_id:
            continue
        if m.type not in movement_types:
            continue
        if abs(Decimal(str(m.amount)) - target) > _AMOUNT_TOLERANCE:
            continue
        occurred = _as_utc(m.occurred_at)
        if occurred < window_start or occurred > window_end:
            continue
        if m.movement_id in taken:
            continue
        candidates.append(m)

    entry_midpoint = datetime.combine(entry_date, time(12), tzinfo=timezone.utc)
    return sorted(candidates, key=lambda m: abs(_as_utc(m.occurred_at) - entry_midpoint))


# ── API pública ───────────────────────────────────────────────────────────────

def import_csv(
    db: Session,
    company_id: UUID,
    account_id: UUID,
    file_content: bytes,
    column_mapping: dict,
    created_by: UUID,
) -> dict:
    """Importa CSV de extrato externo de forma idempotente.

    column_mapping: {"date": idx_ou_nome, "amount": idx_ou_nome,
                     "description": idx_ou_nome?, "direction": idx_ou_nome?}
    Linhas já importadas (mesmo line_hash no tenant) são puladas.
    Linhas com data/valor não parseável (ex.: header) são puladas.
    auto_matched: entries com candidato a match encontrado (apenas sugestão —
    status permanece PENDING).
    """
    if "date" not in column_mapping or "amount" not in column_mapping:
        raise HTTPException(
            status_code=422,
            detail="column_mapping deve conter as chaves 'date' e 'amount'",
        )

    text = file_content.decode("utf-8-sig", errors="replace")
    raw_lines = [ln for ln in text.splitlines() if ln.strip()]
    if not raw_lines:
        raise HTTPException(status_code=422, detail="Arquivo CSV vazio")

    # Header só é necessário quando o mapping usa nomes de coluna
    uses_names = any(
        not (isinstance(v, int) or (isinstance(v, str) and v.lstrip("-").isdigit()))
        for v in column_mapping.values()
        if v is not None
    )
    header: Optional[list[str]] = None
    if uses_names:
        header = [c.strip() for c in next(csv.reader([raw_lines[0]]))]

    # Hashes já importados pelo tenant (idempotência de re-upload)
    existing_rows = (
        db.query(ExternalStatementEntry.line_hash)
        .filter(ExternalStatementEntry.company_id == company_id)
        .all()
    )
    existing_hashes = {row[0] for row in existing_rows}

    # Movements já casados — evita sugerir o mesmo movement duas vezes no batch
    taken_movements = _matched_movement_ids(company_id, db)

    batch_id = uuid_mod.uuid4()
    imported = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    auto_matched = 0
    seen_in_file: set[str] = set()

    for raw_line in raw_lines:
        row = next(csv.reader([raw_line]))

        date_cell = _cell(row, header, column_mapping.get("date"))
        amount_cell = _cell(row, header, column_mapping.get("amount"))
        occurred = _parse_date(date_cell) if date_cell else None
        amount = _parse_amount(amount_cell) if amount_cell else None
        if occurred is None or amount is None:
            # header ou linha malformada
            skipped_invalid += 1
            continue

        lhash = _line_hash(raw_line)
        if lhash in existing_hashes or lhash in seen_in_file:
            skipped_duplicates += 1
            continue
        seen_in_file.add(lhash)

        direction_cell = _cell(row, header, column_mapping.get("direction"))
        direction = _infer_direction(direction_cell, amount)
        description_cell = _cell(row, header, column_mapping.get("description"))

        entry = ExternalStatementEntry(
            company_id=company_id,
            account_id=account_id,
            occurred_at=occurred,
            amount=abs(amount),
            direction=direction,
            description=(description_cell or "").strip()[:500] or None,
            raw_line=raw_line,
            line_hash=lhash,
            status="PENDING",
            import_batch_id=batch_id,
        )
        db.add(entry)
        imported += 1

        # Sugestão automática — nada é persistido como MATCHED
        candidates = _find_candidates(
            entry_account_id=account_id,
            entry_amount=abs(amount),
            entry_direction=direction,
            entry_date=occurred,
            company_id=company_id,
            db=db,
            exclude_movement_ids=taken_movements,
        )
        if candidates:
            auto_matched += 1

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=created_by,
            actor_role="OWNER",
            action="statement_import",
            resource_type="ExternalStatementEntry",
            resource_id=batch_id,
            company_id=company_id,
            account_id=account_id,
            after_snapshot={
                "imported": imported,
                "skipped_duplicates": skipped_duplicates,
                "skipped_invalid": skipped_invalid,
                "auto_matched": auto_matched,
            },
        ),
        db,
    )
    db.commit()

    _publish(
        "statement.batch_imported",
        company_id,
        f"statement.import:{batch_id}",
        {
            "batch_id": str(batch_id),
            "account_id": str(account_id),
            "imported": imported,
            "skipped_duplicates": skipped_duplicates,
            "auto_matched": auto_matched,
        },
    )

    return {
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "auto_matched": auto_matched,
        "batch_id": batch_id,
    }


def suggest_match(db: Session, company_id: UUID, entry_id: UUID) -> list[Movement]:
    """Candidatos a match para uma entry PENDING — APENAS sugestão, zero persistência."""
    entry = _get_entry(entry_id, company_id, db)
    if entry.status != "PENDING":
        raise HTTPException(
            status_code=422,
            detail=f"Entry com status {entry.status} não aceita sugestões de match",
        )
    return _find_candidates(
        entry_account_id=entry.account_id,
        entry_amount=Decimal(str(entry.amount)),
        entry_direction=entry.direction,
        entry_date=entry.occurred_at,
        company_id=company_id,
        db=db,
    )


def confirm_match(
    db: Session,
    company_id: UUID,
    entry_id: UUID,
    movement_id: UUID,
    confirmed_by: UUID,
) -> ExternalStatementEntry:
    """Vincula entry a Movement. Vínculo UNIDIRECIONAL — Movement nunca é alterado."""
    entry = _get_entry(entry_id, company_id, db)
    if entry.status != "PENDING":
        raise HTTPException(
            status_code=422,
            detail=f"Entry com status {entry.status} não pode ser casada (apenas PENDING)",
        )

    movement = (
        db.query(Movement)
        .filter(
            Movement.movement_id == movement_id,
            Movement.company_id == company_id,
        )
        .first()
    )
    if not movement:
        raise HTTPException(status_code=404, detail="Movement não encontrado")

    already_matched = (
        db.query(ExternalStatementEntry)
        .filter(
            ExternalStatementEntry.company_id == company_id,
            ExternalStatementEntry.matched_movement_id == movement_id,
            ExternalStatementEntry.id != entry_id,
        )
        .first()
    )
    if already_matched:
        raise HTTPException(
            status_code=409,
            detail="Movement já está casado com outro lançamento de extrato",
        )

    entry.status = "MATCHED"
    entry.matched_movement_id = movement_id

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=confirmed_by,
            actor_role="OWNER",
            action="statement_confirm_match",
            resource_type="ExternalStatementEntry",
            resource_id=entry.id,
            company_id=company_id,
            amount=Decimal(str(entry.amount)),
            account_id=entry.account_id,
            after_snapshot={"matched_movement_id": str(movement_id)},
        ),
        db,
    )
    db.commit()
    db.refresh(entry)

    _publish(
        "statement.entry_matched",
        company_id,
        f"statement.matched:{entry_id}",
        {"entry_id": str(entry_id), "movement_id": str(movement_id)},
    )
    return entry


def dismiss_entry(
    db: Session,
    company_id: UUID,
    entry_id: UUID,
    reason: Optional[str],
    dismissed_by: UUID,
) -> ExternalStatementEntry:
    """Dispensa entry PENDING. reason é obrigatório."""
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=422,
            detail="reason é obrigatório para dispensar um lançamento de extrato",
        )

    entry = _get_entry(entry_id, company_id, db)
    if entry.status != "PENDING":
        raise HTTPException(
            status_code=422,
            detail=f"Entry com status {entry.status} não pode ser dispensada (apenas PENDING)",
        )

    now = datetime.now(timezone.utc)
    entry.status = "DISMISSED"
    entry.dismissed_reason = reason.strip()[:255]
    entry.dismissed_at = now
    entry.dismissed_by = dismissed_by

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=dismissed_by,
            actor_role="OWNER",
            action="statement_dismiss",
            resource_type="ExternalStatementEntry",
            resource_id=entry.id,
            company_id=company_id,
            reason=reason.strip()[:255],
            account_id=entry.account_id,
        ),
        db,
    )
    db.commit()
    db.refresh(entry)

    _publish(
        "statement.entry_dismissed",
        company_id,
        f"statement.dismissed:{entry_id}",
        {"entry_id": str(entry_id), "reason": entry.dismissed_reason},
    )
    return entry


# ── queries ───────────────────────────────────────────────────────────────────

def list_statement_entries(
    company_id: UUID,
    db: Session,
    account_id: Optional[UUID] = None,
    status: Optional[str] = None,
    batch_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
) -> list[ExternalStatementEntry]:
    query = db.query(ExternalStatementEntry).filter(
        ExternalStatementEntry.company_id == company_id
    )
    if account_id:
        query = query.filter(ExternalStatementEntry.account_id == account_id)
    if status:
        query = query.filter(ExternalStatementEntry.status == status)
    if batch_id:
        query = query.filter(ExternalStatementEntry.import_batch_id == batch_id)
    if date_from:
        query = query.filter(ExternalStatementEntry.occurred_at >= date_from)
    if date_to:
        query = query.filter(ExternalStatementEntry.occurred_at <= date_to)
    return query.order_by(ExternalStatementEntry.occurred_at.desc()).all()


def list_batches(company_id: UUID, db: Session) -> list[dict]:
    """Resumo por import_batch_id: total/matched/pending/dismissed."""
    entries = (
        db.query(ExternalStatementEntry)
        .filter(ExternalStatementEntry.company_id == company_id)
        .all()
    )
    batches: dict = {}
    for e in entries:
        b = batches.setdefault(e.import_batch_id, {
            "batch_id": e.import_batch_id,
            "account_id": e.account_id,
            "imported_at": e.imported_at,
            "total": 0,
            "matched": 0,
            "pending": 0,
            "dismissed": 0,
        })
        b["total"] += 1
        if e.status == "MATCHED":
            b["matched"] += 1
        elif e.status == "DISMISSED":
            b["dismissed"] += 1
        else:
            b["pending"] += 1
        if e.imported_at and (b["imported_at"] is None or e.imported_at < b["imported_at"]):
            b["imported_at"] = e.imported_at
    return sorted(
        batches.values(),
        key=lambda b: b["imported_at"] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
