"""ExpensesService — Sprint 18.

Lifecycle: PENDENTE → PAGA | CANCELLED

create_expense:  cria despesa; se recurrence_rule, gera a próxima instância
                 encadeada (parent_expense_id).
pay_expense:     PENDENTE → PAGA; Movement OUTFLOW + Entry DESPESA atômicos
                 via financial_core.handle_expense_paid; próxima instância
                 da recorrência gerada FORA da transação de pagamento.
cancel_expense:  PENDENTE → CANCELLED (PAGA não pode ser cancelada).

Recorrência: {"frequency": "MONTHLY", "day_of_month": int, "end_date"?: date}
com clamp de fim de mês (day_of_month=31 em fevereiro → último dia do mês).
"""
from __future__ import annotations

import calendar
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from dateutil.relativedelta import relativedelta
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.domain.enums.entry_category import CATEGORY_TO_ENTRY_TYPE
from app.infrastructure.db.models.expense import Expense
from app.modules.financial_core.service import DESPESA_CATEGORIES, handle_expense_paid

logger = logging.getLogger(__name__)


# ── Validações ────────────────────────────────────────────────────────────────

def _validate_category(category: str) -> None:
    """Categoria deve ser DESPESA. CUSTO pertence ao domínio de Estoque (Sprint 17)."""
    entry_type = CATEGORY_TO_ENTRY_TYPE.get(category)
    if entry_type == "CUSTO":
        raise HTTPException(
            status_code=422,
            detail=(
                f"Categoria '{category}' é CUSTO — pertence ao domínio de Estoque "
                "(Sprint 17), não a Despesas"
            ),
        )
    if category not in DESPESA_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Categoria '{category}' não é uma categoria DESPESA válida. "
                f"Permitidas: {sorted(DESPESA_CATEGORIES)}"
            ),
        )


def _validate_recurrence_rule(rule: Optional[dict]) -> None:
    if rule is None:
        return
    if rule.get("frequency") != "MONTHLY":
        raise HTTPException(
            status_code=422,
            detail="recurrence_rule.frequency: apenas MONTHLY é suportado no Estágio 0",
        )
    day = rule.get("day_of_month")
    if not isinstance(day, int) or not (1 <= day <= 31):
        raise HTTPException(
            status_code=422,
            detail="recurrence_rule.day_of_month deve ser inteiro entre 1 e 31",
        )


# ── Recorrência ───────────────────────────────────────────────────────────────

def next_occurrence(base_date: date, rule: dict) -> date:
    """Próxima data MONTHLY com clamp de fim de mês.

    day_of_month=31 em fevereiro → último dia do mês (28/29).
    """
    next_date = base_date + relativedelta(months=1)
    day = rule["day_of_month"]
    max_day = calendar.monthrange(next_date.year, next_date.month)[1]
    return next_date.replace(day=min(day, max_day))


def _has_pending_next_instance(expense: Expense, db: Session) -> bool:
    existing = (
        db.query(Expense)
        .filter(
            Expense.company_id == expense.company_id,
            Expense.parent_expense_id == expense.id,
            Expense.status == "PENDENTE",
        )
        .first()
    )
    return existing is not None


def generate_next_instance(expense: Expense, db: Session) -> Optional[Expense]:
    """Gera a próxima instância da recorrência, se aplicável.

    Idempotente: não cria se já existe próxima PENDENTE encadeada.
    Respeita end_date da regra. Commit próprio — chamar FORA da
    transação de pagamento.
    """
    rule = expense.recurrence_rule
    if not rule:
        return None

    if _has_pending_next_instance(expense, db):
        return None

    next_date = next_occurrence(expense.due_date, rule)

    end_date = rule.get("end_date")
    if end_date:
        if isinstance(end_date, str):
            end_date = date.fromisoformat(end_date)
        if next_date > end_date:
            return None

    next_expense = Expense(
        id=uuid.uuid4(),
        company_id=expense.company_id,
        description=expense.description,
        amount=expense.amount,
        category=expense.category,
        supplier_id=expense.supplier_id,
        due_date=next_date,
        status="PENDENTE",
        recurrence_rule=rule,
        parent_expense_id=expense.id,
        created_by=expense.created_by,
    )
    db.add(next_expense)
    db.commit()
    db.refresh(next_expense)
    return next_expense


# ── API pública ───────────────────────────────────────────────────────────────

def create_expense(
    company_id: UUID,
    data: dict,
    created_by: UUID,
    db: Session,
) -> Expense:
    """Cria despesa PENDENTE. Se recurrence_rule: gera a próxima instância encadeada."""
    _validate_category(data["category"])
    rule = data.get("recurrence_rule")
    _validate_recurrence_rule(rule)

    expense = Expense(
        id=uuid.uuid4(),
        company_id=company_id,
        description=data["description"],
        amount=data["amount"],
        category=data["category"],
        supplier_id=data.get("supplier_id"),
        due_date=data["due_date"],
        status="PENDENTE",
        recurrence_rule=rule,
        created_by=created_by,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)

    _publish_event(
        event_type="expense.created",
        idempotency_key=f"expense.created:{expense.id}",
        expense=expense,
    )

    # Próxima instância da recorrência — best-effort, fora da criação principal
    if rule:
        try:
            generate_next_instance(expense, db)
        except Exception:
            db.rollback()
            logger.exception(
                "create_expense: falha ao gerar próxima instância expense_id=%s",
                expense.id,
            )

    return expense


def pay_expense(
    expense_id: UUID,
    company_id: UUID,
    db: Session,
    paid_amount: Optional[Decimal] = None,
) -> Expense:
    """PENDENTE → PAGA. Movement OUTFLOW + Entry DESPESA atômicos.

    A próxima instância da recorrência é gerada FORA da transação de
    pagamento — falha na geração NÃO desfaz o pagamento.
    """
    expense = _get_expense_or_404(expense_id, company_id, db)

    if expense.status != "PENDENTE":
        raise HTTPException(
            status_code=422,
            detail=f"Despesa não está PENDENTE (status={expense.status})",
        )

    _validate_category(expense.category)

    effective_amount = paid_amount if paid_amount is not None else Decimal(str(expense.amount))

    now = datetime.now(timezone.utc)

    # Transação atômica: Movement + Entry + transição de status
    handle_expense_paid(
        expense_id=expense.id,
        amount=effective_amount,
        category=expense.category,
        company_id=company_id,
        db=db,
    )
    expense.status = "PAGA"
    expense.paid_at = now
    expense.paid_amount = effective_amount
    db.commit()
    db.refresh(expense)

    # Próxima instância — fora da transação de pagamento (best-effort)
    if expense.recurrence_rule:
        try:
            generate_next_instance(expense, db)
        except Exception:
            db.rollback()
            logger.exception(
                "pay_expense: falha ao gerar próxima instância expense_id=%s "
                "(pagamento permanece efetivado)",
                expense.id,
            )

    _publish_event(
        event_type="expense.paid",
        idempotency_key=f"expense.paid:{expense.id}",
        expense=expense,
    )

    return expense


def cancel_expense(
    expense_id: UUID,
    company_id: UUID,
    reason: str,
    db: Session,
    actor_id: Optional[UUID] = None,
) -> Expense:
    """PENDENTE → CANCELLED. PAGA não pode ser cancelada."""
    if not reason or not reason.strip():
        raise HTTPException(status_code=422, detail="reason é obrigatório para cancelar despesa")

    expense = _get_expense_or_404(expense_id, company_id, db)

    if expense.status == "PAGA":
        raise HTTPException(
            status_code=422,
            detail="Despesa PAGA não pode ser cancelada",
        )
    if expense.status != "PENDENTE":
        raise HTTPException(
            status_code=422,
            detail=f"Despesa não está PENDENTE (status={expense.status})",
        )

    expense.status = "CANCELLED"
    expense.updated_at = datetime.now(timezone.utc)

    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="OWNER",
            action="cancel_expense",
            resource_type="Expense",
            resource_id=expense.id,
            company_id=company_id,
            reason=reason,
            after_snapshot={"status": "CANCELLED"},
        ),
        db,
    )

    db.commit()
    db.refresh(expense)

    _publish_event(
        event_type="expense.cancelled",
        idempotency_key=f"expense.cancelled:{expense.id}",
        expense=expense,
    )

    return expense


def get_expenses(
    company_id: UUID,
    db: Session,
    status: Optional[str] = None,
    category: Optional[str] = None,
    due_date_from: Optional[date] = None,
    due_date_to: Optional[date] = None,
    supplier_id: Optional[UUID] = None,
) -> List[Expense]:
    """Lista despesas do tenant com filtros opcionais."""
    q = db.query(Expense).filter(Expense.company_id == company_id)
    if status:
        q = q.filter(Expense.status == status)
    if category:
        q = q.filter(Expense.category == category)
    if due_date_from:
        q = q.filter(Expense.due_date >= due_date_from)
    if due_date_to:
        q = q.filter(Expense.due_date <= due_date_to)
    if supplier_id:
        q = q.filter(Expense.supplier_id == supplier_id)
    return q.order_by(Expense.due_date.desc()).all()


def get_expense(expense_id: UUID, company_id: UUID, db: Session) -> Expense:
    return _get_expense_or_404(expense_id, company_id, db)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_expense_or_404(expense_id: UUID, company_id: UUID, db: Session) -> Expense:
    expense = (
        db.query(Expense)
        .filter(Expense.id == expense_id, Expense.company_id == company_id)
        .first()
    )
    if not expense:
        raise HTTPException(status_code=404, detail="Despesa não encontrada")
    return expense


def _publish_event(event_type: str, idempotency_key: str, expense: Expense) -> None:
    """Publica evento no EventBus — best-effort, nunca propaga exceção."""
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=expense.company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": None},
            payload={
                "expense_id": str(expense.id),
                "company_id": str(expense.company_id),
                "category": expense.category,
                "amount": str(expense.amount),
                "status": expense.status,
                "due_date": expense.due_date.isoformat() if expense.due_date else None,
            },
        ))
    except Exception:
        logger.exception("expenses: falha ao publicar %s expense_id=%s", event_type, expense.id)
