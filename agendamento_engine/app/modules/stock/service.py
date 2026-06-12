"""StockService — Sprint 17.

receive_order:   entrada de estoque — SupplierOrder RECEIVED + StockMovements
                 ENTRADA + recálculo de custo médio ponderado + Payable, tudo
                 em UMA transação. SEM Entry CUSTO (Financial-1: receber ≠
                 reconhecer custo).
record_movement: saídas VENDA | USO_INTERNO | PERDA | AJUSTE — decrementa
                 estoque e cria Entry CUSTO/AJUSTE valorizada a avg_cost,
                 SEM Movement (cash flow foi na compra).

Custo médio ponderado:
    avg_cost = (stock * avg_cost + quantity * unit_cost) / (stock + quantity)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.audit.sensitive_context import (
    SensitiveAuditContext,
    record_sensitive_action,
)
from app.infrastructure.db.models.product import Product
from app.infrastructure.db.models.stock_movement import StockMovement
from app.infrastructure.db.models.supplier import Supplier, SupplierOrder
from app.infrastructure.db.models.tenant_config import TenantConfig
from app.modules.financial_core.service import handle_stock_cost_entry
from app.modules.payables import service as payables_service

logger = logging.getLogger(__name__)

OUTBOUND_MOVEMENT_TYPES = {"VENDA", "USO_INTERNO", "PERDA", "AJUSTE"}

# movement_type → categoria de Entry (nomes canônicos de entry_category.py)
MOVEMENT_TYPE_TO_CATEGORY = {
    "VENDA": "PRODUTO_VENDIDO",
    "USO_INTERNO": "INSUMOS_USO_INTERNO",
    "PERDA": "PERDA_ESTOQUE",
    "AJUSTE": "CONTAGEM_ESTOQUE",
}

# movement_type → evento publicado
MOVEMENT_TYPE_TO_EVENT = {
    "VENDA": "stock.sold",
    "USO_INTERNO": "stock.consumed",
    "PERDA": "stock.loss_recorded",
    "AJUSTE": "stock.adjusted",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_product_or_404(product_id: UUID, company_id: UUID, db: Session) -> Product:
    product = (
        db.query(Product)
        .filter(Product.id == product_id, Product.company_id == company_id)
        .first()
    )
    if not product:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return product


def _allow_negative_stock(company_id: UUID, db: Session) -> bool:
    """Default: estoque controlado (False) — inclusive sem TenantConfig."""
    config = (
        db.query(TenantConfig)
        .filter(TenantConfig.company_id == company_id)
        .first()
    )
    return bool(config and config.allow_negative_stock)


def compute_avg_cost(
    current_stock: Decimal,
    current_avg_cost: Optional[Decimal],
    quantity: Decimal,
    unit_cost: Decimal,
) -> Decimal:
    """Custo médio ponderado, arredondado a 2 casas (HALF_UP).

    Estoque atual negativo ou avg_cost nulo entram como zero na ponderação.
    """
    current_stock = max(Decimal(str(current_stock or 0)), Decimal("0"))
    current_avg = Decimal(str(current_avg_cost)) if current_avg_cost is not None else Decimal("0")
    total_qty = current_stock + quantity
    if total_qty <= 0:
        return unit_cost.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    new_avg = (current_stock * current_avg + quantity * unit_cost) / total_qty
    return new_avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _publish_event(event_type: str, idempotency_key: str, company_id: UUID, payload: dict) -> None:
    """Publica evento no EventBus — best-effort, nunca propaga exceção."""
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type=event_type,
            occurred_at=datetime.now(timezone.utc),
            company_id=company_id,
            idempotency_key=idempotency_key,
            actor={"type": "SYSTEM", "id": None},
            payload=payload,
        ))
    except Exception:
        logger.exception("stock: falha ao publicar %s", event_type)


# ── API pública ───────────────────────────────────────────────────────────────

def receive_order(
    company_id: UUID,
    supplier_id: Optional[UUID],
    items: List[dict],
    created_by: UUID,
    db: Session,
    closing_method: str = "CASH_AT_CREATION",
    installments: Optional[List[dict]] = None,
    due_date=None,
    notes: Optional[str] = None,
) -> tuple[SupplierOrder, "payables_service.Payable"]:
    """Entrada de estoque em UMA transação.

    items: [{product_id, quantity, unit_cost}]
      1. SupplierOrder (status=RECEIVED)
      2. Por item: StockMovement ENTRADA + recálculo de avg_cost + incremento de stock
      3. Payable OPEN (source_type=STOCK_PURCHASE) com installments

    SEM Entry CUSTO aqui — Financial-1: receber ≠ reconhecer custo.
    """
    if not items:
        raise HTTPException(status_code=422, detail="items não pode ser vazio")

    if supplier_id is not None:
        supplier = (
            db.query(Supplier)
            .filter(Supplier.id == supplier_id, Supplier.company_id == company_id)
            .first()
        )
        if not supplier:
            raise HTTPException(status_code=404, detail="Fornecedor não encontrado")

    now = datetime.now(timezone.utc)

    order = SupplierOrder(
        id=uuid.uuid4(),
        company_id=company_id,
        supplier_id=supplier_id,
        status="RECEIVED",
        ordered_at=now,
        received_at=now,
        notes=notes,
        created_by=created_by,
    )
    db.add(order)
    db.flush()

    total_amount = Decimal("0")
    for item in items:
        quantity = Decimal(str(item["quantity"]))
        unit_cost = Decimal(str(item["unit_cost"]))
        if quantity <= 0:
            raise HTTPException(status_code=422, detail="quantity deve ser > 0")
        if unit_cost < 0:
            raise HTTPException(status_code=422, detail="unit_cost não pode ser negativo")

        product = _get_product_or_404(item["product_id"], company_id, db)

        db.add(StockMovement(
            id=uuid.uuid4(),
            company_id=company_id,
            product_id=product.id,
            movement_type="ENTRADA",
            quantity=quantity,
            unit_cost=unit_cost,
            source_type="SUPPLIER_ORDER",
            source_id=order.id,
            occurred_at=now,
            created_by=created_by,
        ))

        product.avg_cost = compute_avg_cost(
            current_stock=Decimal(str(product.stock or 0)),
            current_avg_cost=product.avg_cost,
            quantity=quantity,
            unit_cost=unit_cost,
        )
        product.stock = (product.stock or 0) + int(quantity)

        total_amount += quantity * unit_cost

    db.flush()

    payable = payables_service.create_payable(
        company_id=company_id,
        description=f"Compra de estoque — pedido {order.id}",
        total_amount=total_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        source_type="STOCK_PURCHASE",
        source_id=order.id,
        created_by=created_by,
        db=db,
        supplier_id=supplier_id,
        closing_method=closing_method,
        installments=installments,
        due_date=due_date,
        commit=False,
    )

    db.commit()
    db.refresh(order)
    db.refresh(payable)

    _publish_event(
        event_type="stock.entry_recorded",
        idempotency_key=f"stock.entry_recorded:{order.id}",
        company_id=company_id,
        payload={
            "supplier_order_id": str(order.id),
            "payable_id": str(payable.id),
            "company_id": str(company_id),
            "total_amount": str(payable.total_amount),
            "items": len(items),
            "product_ids": [str(item["product_id"]) for item in items],
        },
    )

    return order, payable


def record_movement(
    company_id: UUID,
    product_id: UUID,
    movement_type: str,
    quantity,
    created_by: UUID,
    db: Session,
    source_type: Optional[str] = None,
    source_id: Optional[UUID] = None,
    notes: Optional[str] = None,
    actor_role: str = "OWNER",
) -> StockMovement:
    """Saída de estoque: VENDA | USO_INTERNO | PERDA | AJUSTE.

    Decrementa product.stock e cria Entry CUSTO/AJUSTE valorizada a avg_cost
    SEM Movement (Financial-1: cash flow foi na compra).

    AJUSTE: quantity é o delta (positivo repõe, negativo baixa); notes
    obrigatório + record_sensitive_action; Entry category=CONTAGEM_ESTOQUE.
    """
    if movement_type not in OUTBOUND_MOVEMENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=(
                f"movement_type '{movement_type}' inválido. "
                f"Permitidos: {sorted(OUTBOUND_MOVEMENT_TYPES)} (ENTRADA via receive_order)"
            ),
        )

    quantity = Decimal(str(quantity))

    if movement_type == "AJUSTE":
        if not notes or not notes.strip():
            raise HTTPException(
                status_code=422,
                detail="notes é obrigatório para movimento AJUSTE",
            )
        if quantity == 0:
            raise HTTPException(status_code=422, detail="quantity não pode ser 0")
    elif quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity deve ser > 0")

    product = _get_product_or_404(product_id, company_id, db)

    current_stock = Decimal(str(product.stock or 0))
    delta = quantity if movement_type == "AJUSTE" else -quantity

    if delta < 0 and current_stock + delta < 0 and not _allow_negative_stock(company_id, db):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Estoque insuficiente para '{product.name}': disponível "
                f"{current_stock}, solicitado {abs(delta)} (controle de estoque ativo)"
            ),
        )

    now = datetime.now(timezone.utc)
    avg_cost = Decimal(str(product.avg_cost)) if product.avg_cost is not None else Decimal("0")
    cost_amount = (abs(delta) * avg_cost).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    movement = StockMovement(
        id=uuid.uuid4(),
        company_id=company_id,
        product_id=product.id,
        movement_type=movement_type,
        quantity=quantity,
        unit_cost=None,  # saídas são valorizadas a avg_cost
        source_type=source_type or ("ADJUSTMENT" if movement_type == "AJUSTE" else "MANUAL"),
        source_id=source_id,
        notes=notes,
        occurred_at=now,
        created_by=created_by,
    )
    db.add(movement)
    db.flush()

    product.stock = int(current_stock + delta)

    # Entry CUSTO/AJUSTE sem Movement (Financial-1) — apenas se houver valor
    entry = None
    if cost_amount > 0:
        direction = "ADDS" if (movement_type == "AJUSTE" and delta > 0) else "SUBTRACTS"
        entry = handle_stock_cost_entry(
            movement_id=movement.id,
            amount=cost_amount,
            category=MOVEMENT_TYPE_TO_CATEGORY[movement_type],
            company_id=company_id,
            db=db,
            direction=direction,
        )

    if movement_type == "AJUSTE":
        record_sensitive_action(
            SensitiveAuditContext(
                actor_id=created_by,
                actor_role=actor_role,
                action="stock_adjustment",
                resource_type="StockMovement",
                resource_id=movement.id,
                company_id=company_id,
                reason=notes,
                amount=cost_amount,
                after_snapshot={
                    "product_id": str(product.id),
                    "quantity": str(quantity),
                    "stock_after": product.stock,
                    "entry_id": str(entry.entry_id) if entry else None,
                },
            ),
            db,
        )

    db.commit()
    db.refresh(movement)

    _publish_event(
        event_type=MOVEMENT_TYPE_TO_EVENT[movement_type],
        idempotency_key=f"{MOVEMENT_TYPE_TO_EVENT[movement_type]}:{movement.id}",
        company_id=company_id,
        payload={
            "stock_movement_id": str(movement.id),
            "product_id": str(product.id),
            "company_id": str(company_id),
            "movement_type": movement_type,
            "quantity": str(quantity),
            "cost_amount": str(cost_amount),
            "stock_after": product.stock,
        },
    )

    return movement


def list_stock(company_id: UUID, db: Session, active_only: bool = True) -> List[Product]:
    """Produtos do tenant com stock atual + avg_cost."""
    q = db.query(Product).filter(Product.company_id == company_id)
    if active_only:
        q = q.filter(Product.active == True)  # noqa: E712
    return q.order_by(Product.name).all()


def list_movements(
    company_id: UUID,
    db: Session,
    product_id: Optional[UUID] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
) -> List[StockMovement]:
    """Histórico de movimentos de estoque com filtros."""
    q = db.query(StockMovement).filter(StockMovement.company_id == company_id)
    if product_id:
        q = q.filter(StockMovement.product_id == product_id)
    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type)
    if date_from:
        q = q.filter(StockMovement.occurred_at >= date_from)
    if date_to:
        q = q.filter(StockMovement.occurred_at <= date_to)
    return q.order_by(StockMovement.occurred_at.desc()).all()
