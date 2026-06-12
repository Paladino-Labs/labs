"""Router de conciliação com extrato externo (Sprint E).

Endpoints:
    POST /financial/statement/import        — import CSV (multipart/form-data)
    GET  /financial/statement/              — lista entries com filtros
    GET  /financial/statement/batches       — resumo por batch de import
    GET  /financial/statement/{id}/suggestions — candidatos a match (só sugestão)
    POST /financial/statement/{id}/match    — confirma match (Movement intocado)
    POST /financial/statement/{id}/dismiss  — dispensa com reason obrigatório

RBAC: writes via require_action — OWNER/ADMIN por padrão; OPERATOR apenas
com permission_overrides["OPERATOR"]["statement_*"] no TenantConfig.
"""
import json
from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.deps import get_current_company_id, require_action, require_role
from app.infrastructure.db.session import get_db
from app.infrastructure.db.models.user import User
from app.modules.financial_core import service, statement_service
from app.modules.financial_core.schemas import (
    MovementResponse,
    StatementBatchSummary,
    StatementDismissBody,
    StatementEntryResponse,
    StatementImportResponse,
    StatementMatchBody,
)

router = APIRouter(prefix="/financial/statement", tags=["financial-statement"])

MAX_CSV_SIZE = 5 * 1024 * 1024  # 5 MB

_owner_admin_operator = require_role("OWNER", "ADMIN", "OPERATOR", "PLATFORM_OWNER")


@router.post("/import", response_model=StatementImportResponse, status_code=201)
async def import_statement(
    file: UploadFile = File(...),
    account_id: UUID = Form(...),
    column_mapping: str = Form(...),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(require_action("statement_import")),
    db: Session = Depends(get_db),
):
    try:
        mapping = json.loads(column_mapping)
    except (json.JSONDecodeError, TypeError):
        raise HTTPException(status_code=422, detail="column_mapping deve ser JSON válido")
    if not isinstance(mapping, dict):
        raise HTTPException(status_code=422, detail="column_mapping deve ser um objeto JSON")

    content = await file.read()
    if len(content) > MAX_CSV_SIZE:
        raise HTTPException(status_code=422, detail="Arquivo muito grande. Máximo: 5 MB")

    # Valida que a conta pertence ao tenant (404 se não)
    service.get_account(account_id, company_id, db)

    result = statement_service.import_csv(
        db=db,
        company_id=company_id,
        account_id=account_id,
        file_content=content,
        column_mapping=mapping,
        created_by=actor.id,
    )
    return StatementImportResponse(**result)


@router.get("/", response_model=List[StatementEntryResponse])
def list_statement_entries(
    account_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    batch_id: Optional[UUID] = Query(None),
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(_owner_admin_operator),
    db: Session = Depends(get_db),
):
    return statement_service.list_statement_entries(
        company_id=company_id,
        db=db,
        account_id=account_id,
        status=status,
        batch_id=batch_id,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/batches", response_model=List[StatementBatchSummary])
def list_statement_batches(
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(require_action("statement_import")),
    db: Session = Depends(get_db),
):
    return statement_service.list_batches(company_id, db)


@router.get("/{entry_id}/suggestions", response_model=List[MovementResponse])
def get_match_suggestions(
    entry_id: UUID,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(require_action("statement_match")),
    db: Session = Depends(get_db),
):
    return statement_service.suggest_match(db, company_id, entry_id)


@router.post("/{entry_id}/match", response_model=StatementEntryResponse)
def confirm_statement_match(
    entry_id: UUID,
    body: StatementMatchBody,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(require_action("statement_match")),
    db: Session = Depends(get_db),
):
    return statement_service.confirm_match(
        db=db,
        company_id=company_id,
        entry_id=entry_id,
        movement_id=body.movement_id,
        confirmed_by=actor.id,
    )


@router.post("/{entry_id}/dismiss", response_model=StatementEntryResponse)
def dismiss_statement_entry(
    entry_id: UUID,
    body: StatementDismissBody,
    company_id: UUID = Depends(get_current_company_id),
    actor: User = Depends(require_action("statement_dismiss")),
    db: Session = Depends(get_db),
):
    return statement_service.dismiss_entry(
        db=db,
        company_id=company_id,
        entry_id=entry_id,
        reason=body.reason,
        dismissed_by=actor.id,
    )
