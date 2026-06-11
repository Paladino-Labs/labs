"""SupplierService — Sprint 17.

Fornecedor é desativável, nunca deletado (Princípio 10).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.supplier import Supplier


def _get_supplier_or_404(supplier_id: UUID, company_id: UUID, db: Session) -> Supplier:
    supplier = (
        db.query(Supplier)
        .filter(Supplier.id == supplier_id, Supplier.company_id == company_id)
        .first()
    )
    if not supplier:
        raise HTTPException(status_code=404, detail="Fornecedor não encontrado")
    return supplier


def create_supplier(company_id: UUID, data: dict, db: Session) -> Supplier:
    supplier = Supplier(
        company_id=company_id,
        name=data["name"],
        contact=data.get("contact"),
        document=data.get("document"),
        active=True,
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(supplier_id: UUID, company_id: UUID, data: dict, db: Session) -> Supplier:
    supplier = _get_supplier_or_404(supplier_id, company_id, db)
    for field in ("name", "contact", "document", "active"):
        if field in data and data[field] is not None:
            setattr(supplier, field, data[field])
    supplier.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(supplier)
    return supplier


def deactivate_supplier(supplier_id: UUID, company_id: UUID, db: Session) -> Supplier:
    """Soft delete — Princípio 10: fornecedor nunca é apagado."""
    supplier = _get_supplier_or_404(supplier_id, company_id, db)
    supplier.active = False
    supplier.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(supplier)
    return supplier


def list_suppliers(
    company_id: UUID,
    db: Session,
    active: Optional[bool] = True,
) -> List[Supplier]:
    """Lista fornecedores. Default: apenas ativos (active=None lista todos)."""
    q = db.query(Supplier).filter(Supplier.company_id == company_id)
    if active is not None:
        q = q.filter(Supplier.active == active)
    return q.order_by(Supplier.name).all()


def get_supplier(supplier_id: UUID, company_id: UUID, db: Session) -> Supplier:
    return _get_supplier_or_404(supplier_id, company_id, db)
