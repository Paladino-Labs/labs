"""FinancialCoreEngine — serviço central do módulo financeiro.

API pública (queries):
    get_account, list_accounts, compute_balance, list_movements,
    list_entries, aggregate_dre, create_manual_adjustment

Handlers públicos (chamados por outros módulos/eventos):
    handle_payment_confirmed
    handle_commission_paid
    handle_expense_paid

API privada (apenas handlers internos):
    _record_movement, _record_entry
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.domain.enums.entry_category import CATEGORY_TO_ENTRY_TYPE
from app.infrastructure.db.models.account import Account
from app.infrastructure.db.models.entry import Entry
from app.infrastructure.db.models.movement import Movement
from app.infrastructure.db.models.tenant_fee_routing_policy import TenantFeeRoutingPolicy
from app.modules.financial_core.schemas import MovementFilters, EntryFilters


# ── helpers internos ──────────────────────────────────────────────────────────

def _get_fee_routing_policy(
    fee_source: str,
    company_id: UUID,
    db: Session,
) -> TenantFeeRoutingPolicy:
    """Retorna a política de rateio. Fallback: tenant_share=100% (sem repasse)."""
    policy = (
        db.query(TenantFeeRoutingPolicy)
        .filter(
            TenantFeeRoutingPolicy.company_id == company_id,
            TenantFeeRoutingPolicy.fee_source == fee_source,
        )
        .first()
    )
    if policy is None:
        # Fallback: cria objeto em memória sem persistir
        policy = TenantFeeRoutingPolicy(
            policy_id=uuid.uuid4(),
            company_id=company_id,
            fee_source=fee_source,
            client_share=Decimal("0"),
            tenant_share=Decimal("100"),
            professional_share=Decimal("0"),
        )
    return policy


# ── API privada ───────────────────────────────────────────────────────────────

def _record_movement(
    account_id: UUID,
    type: str,
    amount: Decimal,
    source_type: str,
    source_id: UUID,
    transfer_id: Optional[UUID] = None,
    occurred_at: Optional[datetime] = None,
    company_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> Movement:
    """Cria e persiste um Movement (flush sem commit — responsabilidade do chamador)."""
    movement = Movement(
        company_id=company_id,
        account_id=account_id,
        type=type,
        amount=amount,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        source_type=source_type,
        source_id=source_id,
        transfer_id=transfer_id,
    )
    db.add(movement)
    db.flush()
    return movement


def _record_entry(
    type: str,
    direction: str,
    amount: Decimal,
    category: str,
    source_type: str,
    source_id: UUID,
    movement_id: Optional[UUID] = None,
    occurred_at: Optional[datetime] = None,
    company_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> Entry:
    """Cria e persiste uma Entry (flush sem commit — responsabilidade do chamador)."""
    entry = Entry(
        company_id=company_id,
        type=type,
        direction=direction,
        amount=amount,
        occurred_at=occurred_at or datetime.now(timezone.utc),
        category=category,
        source_type=source_type,
        source_id=source_id,
        movement_id=movement_id,
    )
    db.add(entry)
    db.flush()
    return entry


# ── Handlers públicos ─────────────────────────────────────────────────────────

def handle_payment_confirmed(
    payment_id: UUID,
    gross_amount: Decimal,
    provider_fee: Decimal,
    target_account_id: UUID,
    fee_source: Optional[str],
    company_id: UUID,
    db: Session,
) -> dict:
    """Cria atomicamente os Movements e Entries de um pagamento confirmado.

    Sempre cria:
        Movement INFLOW  gross_amount  → target_account
        Entry   RECEITA  gross_amount  (category SERVICOS)

    Se provider_fee > 0:
        Movement OUTFLOW  provider_fee  → target_account (taxa descontada pela adquirente)
        Entry   TAXA      provider_fee  (category derivada de fee_source via policy)

    Não chama CommunicationService — comunicação via EventBus fora desta transação.
    Commit é responsabilidade do chamador (permite composição em transações maiores).
    """
    now = datetime.now(timezone.utc)
    source_type = "payment"
    source_id = payment_id

    # 1. Movement INFLOW
    inflow = _record_movement(
        account_id=target_account_id,
        type="INFLOW",
        amount=gross_amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    # 2. Entry RECEITA
    receita_entry = _record_entry(
        type="RECEITA",
        direction="ADDS",
        amount=gross_amount,
        category="SERVICOS",
        source_type=source_type,
        source_id=source_id,
        movement_id=inflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    outflow = None
    taxa_entry = None

    if provider_fee > 0:
        # Determina categoria da taxa via policy (para fins de rastreabilidade)
        # ANTECIPACAO → ANTECIPATION_FEE; demais → ACQUIRER_FEE
        taxa_category = "ACQUIRER_FEE"
        if fee_source == "ANTECIPACAO":
            taxa_category = "ANTECIPATION_FEE"

        # 3. Movement OUTFLOW (taxa descontada pelo adquirente)
        outflow = _record_movement(
            account_id=target_account_id,
            type="OUTFLOW",
            amount=provider_fee,
            source_type=source_type,
            source_id=source_id,
            occurred_at=now,
            company_id=company_id,
            db=db,
        )

        # 4. Entry TAXA
        taxa_entry = _record_entry(
            type="TAXA",
            direction="SUBTRACTS",
            amount=provider_fee,
            category=taxa_category,
            source_type=source_type,
            source_id=source_id,
            movement_id=outflow.movement_id,
            occurred_at=now,
            company_id=company_id,
            db=db,
        )

    return {
        "inflow_movement_id": inflow.movement_id,
        "receita_entry_id": receita_entry.entry_id,
        "outflow_movement_id": outflow.movement_id if outflow else None,
        "taxa_entry_id": taxa_entry.entry_id if taxa_entry else None,
    }


def handle_payment_refunded(
    payment_id: UUID,
    gross_amount: Decimal,
    target_account_id: UUID,
    company_id: UUID,
    db: Session,
) -> dict:
    """Cria atomicamente Movement OUTFLOW + Entry ESTORNO para um reembolso.

    Commit é responsabilidade do chamador (permite composição em transações maiores).
    """
    now = datetime.now(timezone.utc)
    source_type = "refund"
    source_id = payment_id

    outflow = _record_movement(
        account_id=target_account_id,
        type="OUTFLOW",
        amount=gross_amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    estorno_entry = _record_entry(
        type="ESTORNO",
        direction="SUBTRACTS",
        amount=gross_amount,
        category="REEMBOLSO_CLIENTE",
        source_type=source_type,
        source_id=source_id,
        movement_id=outflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    return {
        "outflow_movement_id": outflow.movement_id,
        "estorno_entry_id": estorno_entry.entry_id,
    }


def handle_subscription_renewed(
    subscription_id: UUID,
    plan_price: Decimal,
    target_account_id: UUID,
    company_id: UUID,
    db: Session,
) -> dict:
    """Cria Entry RECEITA ASSINATURA_RENOVACAO para renovação de assinatura.

    Cria Movement INFLOW + Entry RECEITA ASSINATURA_RENOVACAO.
    Commit é responsabilidade do chamador.
    """
    now = datetime.now(timezone.utc)
    source_type = "subscription"
    source_id = subscription_id

    inflow = _record_movement(
        account_id=target_account_id,
        type="INFLOW",
        amount=plan_price,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    entry = _record_entry(
        type="RECEITA",
        direction="ADDS",
        amount=plan_price,
        category="ASSINATURA_RENOVACAO",
        source_type=source_type,
        source_id=source_id,
        movement_id=inflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    return {
        "inflow_movement_id": inflow.movement_id,
        "entry_id": entry.entry_id,
    }


def handle_deposit_balance_recognized(
    appointment_id: UUID,
    amount: Decimal,
    target_account_id: UUID,
    company_id: UUID,
    db: Session,
) -> dict:
    """Reconhece o saldo restante de um agendamento com sinal ao concluir.

    Usado pelo fluxo DEPOSIT (Sprint 25): ao COMPLETED, o saldo não coberto
    pelo sinal já confirmado é reconhecido como receita.
    Cria Movement INFLOW + Entry RECEITA (category SERVICOS).
    Commit é responsabilidade do chamador.
    """
    now = datetime.now(timezone.utc)
    source_type = "appointment_balance"
    source_id = appointment_id

    inflow = _record_movement(
        account_id=target_account_id,
        type="INFLOW",
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    entry = _record_entry(
        type="RECEITA",
        direction="ADDS",
        amount=amount,
        category="SERVICOS",
        source_type=source_type,
        source_id=source_id,
        movement_id=inflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    return {
        "inflow_movement_id": inflow.movement_id,
        "entry_id": entry.entry_id,
    }


# ── API pública — queries ─────────────────────────────────────────────────────

def get_account(account_id: UUID, company_id: UUID, db: Session) -> Account:
    account = (
        db.query(Account)
        .filter(Account.account_id == account_id, Account.company_id == company_id)
        .first()
    )
    if not account:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return account


def list_accounts(company_id: UUID, db: Session) -> list[Account]:
    return (
        db.query(Account)
        .filter(Account.company_id == company_id)
        .order_by(Account.created_at)
        .all()
    )


def create_account(
    company_id: UUID,
    name: str,
    type: str,
    provider: Optional[str] = None,
    external_ref: Optional[str] = None,
    currency: str = "BRL",
    is_default_inflow: bool = False,
    db: Optional[Session] = None,
) -> Account:
    account = Account(
        company_id=company_id,
        name=name,
        type=type,
        provider=provider,
        external_ref=external_ref,
        currency=currency,
        is_default_inflow=is_default_inflow,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def compute_balance(
    account_id: UUID,
    as_of: Optional[datetime] = None,
    company_id: Optional[UUID] = None,
    db: Optional[Session] = None,
) -> Decimal:
    """Calcula o saldo da conta somando INFLOW/TRANSFER_IN e subtraindo OUTFLOW/TRANSFER_OUT.

    Se as_of for fornecido, considera apenas movements com occurred_at <= as_of.
    """
    query = db.query(Movement).filter(Movement.account_id == account_id)
    if company_id:
        query = query.filter(Movement.company_id == company_id)
    if as_of:
        query = query.filter(Movement.occurred_at <= as_of)

    movements = query.all()

    balance = Decimal("0")
    for m in movements:
        if m.type in ("INFLOW", "TRANSFER_IN"):
            balance += m.amount
        elif m.type in ("OUTFLOW", "TRANSFER_OUT"):
            balance -= m.amount

    return balance


def list_movements(
    company_id: UUID,
    filters: MovementFilters,
    db: Session,
) -> list[Movement]:
    query = db.query(Movement).filter(Movement.company_id == company_id)

    if filters.account_id:
        query = query.filter(Movement.account_id == filters.account_id)
    if filters.type:
        query = query.filter(Movement.type == filters.type)
    if filters.date_from:
        query = query.filter(Movement.occurred_at >= filters.date_from)
    if filters.date_to:
        query = query.filter(Movement.occurred_at <= filters.date_to)

    return query.order_by(Movement.occurred_at.desc()).all()


def list_entries(
    company_id: UUID,
    filters: EntryFilters,
    db: Session,
) -> list[Entry]:
    query = db.query(Entry).filter(Entry.company_id == company_id)

    if filters.type:
        query = query.filter(Entry.type == filters.type)
    if filters.category:
        query = query.filter(Entry.category == filters.category)
    if filters.date_from:
        query = query.filter(Entry.occurred_at >= filters.date_from)
    if filters.date_to:
        query = query.filter(Entry.occurred_at <= filters.date_to)

    return query.order_by(Entry.occurred_at.desc()).all()


def aggregate_dre(
    company_id: UUID,
    date_from: datetime,
    date_to: datetime,
    db: Session,
) -> dict:
    """Agrega entries por tipo e categoria para o DRE do período."""
    entries = (
        db.query(Entry)
        .filter(
            Entry.company_id == company_id,
            Entry.occurred_at >= date_from,
            Entry.occurred_at <= date_to,
        )
        .all()
    )

    buckets: dict[str, dict[str, Decimal]] = {
        "RECEITA": {},
        "CUSTO": {},
        "DESPESA": {},
        "TAXA": {},
        "COMISSAO": {},
        "ESTORNO": {},
        "AJUSTE": {},
    }

    for e in entries:
        entry_type = e.type
        category = e.category
        amount = Decimal(str(e.amount))

        if entry_type not in buckets:
            buckets[entry_type] = {}

        buckets[entry_type][category] = (
            buckets[entry_type].get(category, Decimal("0")) + amount
        )

    def _total(bucket_name: str) -> Decimal:
        return sum(buckets[bucket_name].values(), Decimal("0"))

    receita_total = _total("RECEITA")
    custo_total = _total("CUSTO")
    despesa_total = _total("DESPESA")
    taxa_total = _total("TAXA")
    comissao_total = _total("COMISSAO")
    estorno_total = _total("ESTORNO")
    ajuste_total = _total("AJUSTE")

    resultado_bruto = receita_total - custo_total
    resultado_liquido = (
        resultado_bruto
        - despesa_total
        - taxa_total
        - comissao_total
        + estorno_total
        + ajuste_total
    )

    return {
        "date_from": date_from,
        "date_to": date_to,
        "receita": buckets["RECEITA"],
        "receita_total": receita_total,
        "custo": buckets["CUSTO"],
        "custo_total": custo_total,
        "despesa": buckets["DESPESA"],
        "despesa_total": despesa_total,
        "taxa": buckets["TAXA"],
        "taxa_total": taxa_total,
        "comissao": buckets["COMISSAO"],
        "comissao_total": comissao_total,
        "estorno": buckets["ESTORNO"],
        "estorno_total": estorno_total,
        "ajuste": buckets["AJUSTE"],
        "ajuste_total": ajuste_total,
        "resultado_bruto": resultado_bruto,
        "resultado_liquido": resultado_liquido,
    }


# ── Manual adjustment ─────────────────────────────────────────────────────────

def create_manual_adjustment(
    amount: Decimal,
    direction: str,
    category: str,
    account_id: UUID,
    reason: str,
    actor_id: UUID,
    company_id: UUID,
    db: Session,
) -> tuple[Movement, Entry]:
    """Cria ajuste manual: Movement + Entry na mesma transação.

    reason é obrigatório — gravado em audit_log via record_sensitive_action.
    """
    if not reason or not reason.strip():
        raise HTTPException(
            status_code=422,
            detail="reason é obrigatório para create_manual_adjustment",
        )

    # Valida que a conta pertence ao tenant
    get_account(account_id, company_id, db)

    # Determina tipo do Entry a partir da categoria
    entry_type = CATEGORY_TO_ENTRY_TYPE.get(category, "AJUSTE")

    now = datetime.now(timezone.utc)
    source_id = uuid.uuid4()  # ID sintético para ajuste manual
    source_type = "manual_adjustment"

    movement_type = "INFLOW" if direction == "ADDS" else "OUTFLOW"

    movement = _record_movement(
        account_id=account_id,
        type=movement_type,
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    entry = _record_entry(
        type=entry_type,
        direction=direction,
        amount=amount,
        category=category,
        source_type=source_type,
        source_id=source_id,
        movement_id=movement.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    # Audit trail obrigatório
    record_sensitive_action(
        SensitiveAuditContext(
            actor_id=actor_id,
            actor_role="OWNER",  # será sobrescrito pelo chamador se necessário
            action="create_manual_adjustment",
            resource_type="Movement",
            resource_id=movement.movement_id,
            company_id=company_id,
            reason=reason,
            amount=amount,
            account_id=account_id,
            after_snapshot={
                "direction": direction,
                "category": category,
                "movement_type": movement_type,
                "entry_type": entry_type,
            },
        ),
        db,
    )

    db.commit()
    db.refresh(movement)
    db.refresh(entry)
    return movement, entry


# ── Expense handler ───────────────────────────────────────────────────────────

# Categorias permitidas para Entry DESPESA (derivadas do enum canônico)
DESPESA_CATEGORIES: set[str] = {
    category for category, entry_type in CATEGORY_TO_ENTRY_TYPE.items()
    if entry_type == "DESPESA"
}


def handle_expense_paid(
    expense_id: UUID,
    amount: Decimal,
    category: str,
    company_id: UUID,
    db: Session,
    account_id: Optional[UUID] = None,
) -> tuple[Movement, Entry]:
    """Cria atomicamente Movement OUTFLOW + Entry DESPESA para uma despesa paga.

    Mesmo padrão de handle_payment_confirmed: Movement primeiro, Entry
    referencia o Movement; flush sem commit — commit é responsabilidade
    do chamador (permite composição na transação do pay_expense).

    account_id None → resolve a conta padrão (is_default_inflow=True) do tenant.
    category validada contra as categorias DESPESA de entry_category.py (422).
    """
    if category not in DESPESA_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Categoria '{category}' não é uma categoria DESPESA válida. "
                f"Permitidas: {sorted(DESPESA_CATEGORIES)}"
            ),
        )

    if account_id is None:
        account = (
            db.query(Account)
            .filter(Account.company_id == company_id, Account.is_default_inflow == True)  # noqa: E712
            .first()
        )
        if not account:
            raise HTTPException(
                status_code=422,
                detail="Nenhuma conta padrão (is_default_inflow) configurada para a empresa",
            )
        account_id = account.account_id

    now = datetime.now(timezone.utc)
    source_type = "expense"
    source_id = expense_id

    outflow = _record_movement(
        account_id=account_id,
        type="OUTFLOW",
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    despesa_entry = _record_entry(
        type="DESPESA",
        direction="SUBTRACTS",
        amount=amount,
        category=category,
        source_type=source_type,
        source_id=source_id,
        movement_id=outflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    return outflow, despesa_entry


# ── Stock handlers (Sprint 17) ────────────────────────────────────────────────

# Categorias permitidas para Entry de custo de estoque (Financial-1)
STOCK_COST_CATEGORIES: set[str] = {
    category for category, entry_type in CATEGORY_TO_ENTRY_TYPE.items()
    if entry_type == "CUSTO"
} | {"CONTAGEM_ESTOQUE"}


def handle_stock_cost_entry(
    movement_id: UUID,
    amount: Decimal,
    category: str,
    company_id: UUID,
    db: Session,
    direction: str = "SUBTRACTS",
) -> Entry:
    """Cria Entry de custo de estoque SEM Movement (Financial-1).

    O cash flow ocorreu na compra (Payable/installment) — consumir, vender
    ou perder estoque reconhece o custo sem mexer no caixa.

    category: PRODUTO_VENDIDO | INSUMOS_USO_INTERNO | PERDA_ESTOQUE |
              CONTAGEM_ESTOQUE (AJUSTE) — validada contra entry_category.py.
    Flush sem commit — commit é responsabilidade do chamador (record_movement).
    """
    if category not in STOCK_COST_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Categoria '{category}' não é válida para custo de estoque. "
                f"Permitidas: {sorted(STOCK_COST_CATEGORIES)}"
            ),
        )

    entry_type = CATEGORY_TO_ENTRY_TYPE.get(category, "AJUSTE")

    return _record_entry(
        type=entry_type,
        direction=direction,
        amount=amount,
        category=category,
        source_type="stock_movement",
        source_id=movement_id,
        movement_id=None,
        occurred_at=datetime.now(timezone.utc),
        company_id=company_id,
        db=db,
    )


def handle_payable_installment_paid(
    installment_id: UUID,
    amount: Decimal,
    company_id: UUID,
    db: Session,
    account_id: Optional[UUID] = None,
) -> Movement:
    """Cria Movement OUTFLOW SEM Entry para parcela de Payable paga (Financial-1).

    O custo já foi (ou será) reconhecido pelos movimentos de estoque —
    pagar a parcela é só saída de caixa.

    account_id None → resolve a conta padrão (is_default_inflow=True) do tenant.
    Flush sem commit — commit é responsabilidade do chamador (pay_installment).
    """
    if account_id is None:
        account = (
            db.query(Account)
            .filter(Account.company_id == company_id, Account.is_default_inflow == True)  # noqa: E712
            .first()
        )
        if not account:
            raise HTTPException(
                status_code=422,
                detail="Nenhuma conta padrão (is_default_inflow) configurada para a empresa",
            )
        account_id = account.account_id

    return _record_movement(
        account_id=account_id,
        type="OUTFLOW",
        amount=amount,
        source_type="payable_installment",
        source_id=installment_id,
        occurred_at=datetime.now(timezone.utc),
        company_id=company_id,
        db=db,
    )


# ── Commission handler ────────────────────────────────────────────────────────

def handle_commission_paid(
    payout_id: UUID,
    amount: Decimal,
    account_id: UUID,
    professional_id: UUID,
    company_id: UUID,
    db: Session,
) -> tuple:
    """Cria Movement OUTFLOW + Entry COMISSAO para um payout de comissão.

    Commit é responsabilidade do chamador (permite composição em transações maiores).
    """
    now = datetime.now(timezone.utc)
    source_type = "commission_payout"
    source_id = payout_id

    outflow = _record_movement(
        account_id=account_id,
        type="OUTFLOW",
        amount=amount,
        source_type=source_type,
        source_id=source_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    commission_entry = _record_entry(
        type="COMISSAO",
        direction="SUBTRACTS",
        amount=amount,
        category="COMISSAO_SERVICO",
        source_type=source_type,
        source_id=source_id,
        movement_id=outflow.movement_id,
        occurred_at=now,
        company_id=company_id,
        db=db,
    )

    return outflow, commission_entry


# ── Fee routing ───────────────────────────────────────────────────────────────

def list_fee_routing_policies(company_id: UUID, db: Session) -> list[TenantFeeRoutingPolicy]:
    return (
        db.query(TenantFeeRoutingPolicy)
        .filter(TenantFeeRoutingPolicy.company_id == company_id)
        .order_by(TenantFeeRoutingPolicy.fee_source)
        .all()
    )


def get_fee_routing_policy_or_404(
    fee_source: str, company_id: UUID, db: Session
) -> TenantFeeRoutingPolicy:
    policy = (
        db.query(TenantFeeRoutingPolicy)
        .filter(
            TenantFeeRoutingPolicy.company_id == company_id,
            TenantFeeRoutingPolicy.fee_source == fee_source,
        )
        .first()
    )
    if not policy:
        raise HTTPException(
            status_code=404,
            detail=f"Política de roteio para '{fee_source}' não encontrada",
        )
    return policy


def update_fee_routing_policy(
    fee_source: str,
    client_share: Decimal,
    tenant_share: Decimal,
    professional_share: Decimal,
    company_id: UUID,
    db: Session,
) -> TenantFeeRoutingPolicy:
    """Atualiza as shares de rateio. Valida soma = 100 antes de persistir."""
    total = client_share + tenant_share + professional_share
    if total != Decimal("100"):
        raise HTTPException(
            status_code=422,
            detail=(
                f"A soma de client_share + tenant_share + professional_share deve ser 100. "
                f"Recebido: {total}"
            ),
        )

    policy = get_fee_routing_policy_or_404(fee_source, company_id, db)
    policy.client_share = client_share
    policy.tenant_share = tenant_share
    policy.professional_share = professional_share
    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return policy


def update_fee_policy_calculation(
    fee_source: str,
    company_id: UUID,
    db: Session,
    fee_percentage: Optional[Decimal] = None,
    fee_flat: Optional[Decimal] = None,
    is_active: Optional[bool] = None,
) -> TenantFeeRoutingPolicy:
    """Atualiza taxa MDR de cálculo (fee_percentage, fee_flat, is_active).

    Levanta HTTP 404 se o fee_source não existir para o tenant.
    Validação de range (0-100) é responsabilidade do schema Pydantic chamador.
    """
    policy = get_fee_routing_policy_or_404(fee_source, company_id, db)

    if fee_percentage is not None:
        policy.fee_percentage = fee_percentage
    if fee_flat is not None:
        policy.fee_flat = fee_flat
    if is_active is not None:
        policy.is_active = is_active

    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    return policy
