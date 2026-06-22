"""PackageEngine — Sprint 14.

purchase():   cria PackagePurchase PENDING_PAYMENT + Payment PENDING.
activate():   chamado por handler payment.confirmed; cria CustomerCredit + Commission PACKAGE_SOLD.
              Roda em SessionLocal própria (sessão separada do commit do payment.confirm).
revoke_for_refund(): chamado por handler payment.refunded;
              CustomerCredit REVOKED + Commission REVERSED.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.package import Package, PackagePurchase
from app.infrastructure.db.session import SessionLocal
from app.core.db_rls import set_rls_context

logger = logging.getLogger(__name__)


def purchase(
    customer_id: UUID,
    package_id: UUID,
    seller_user_id: Optional[UUID],
    payment_method: str,
    target_account_id: Optional[UUID],
    company_id: UUID,
    db: Session,
) -> PackagePurchase:
    """Cria PackagePurchase PENDING_PAYMENT + Payment PENDING."""
    package = _get_package_or_404(package_id, company_id, db)

    if not package.is_active:
        raise HTTPException(status_code=422, detail="Pacote inativo — não pode ser vendido")

    pkg_purchase = PackagePurchase(
        purchase_id=uuid.uuid4(),
        company_id=company_id,
        customer_id=customer_id,
        package_id=package_id,
        seller_user_id=seller_user_id,
        total_price=package.price,
        status="PENDING_PAYMENT",
    )
    db.add(pkg_purchase)
    db.flush()

    from app.modules.payments import service as payment_service
    payment = payment_service.create_payment(
        company_id=company_id,
        customer_id=customer_id,
        gross_amount=Decimal(str(package.price)),
        payment_method=payment_method,
        provider="manual",
        target_account_id=target_account_id,
        appointment_id=None,
        db=db,
    )

    pkg_purchase.payment_id = payment.payment_id
    db.commit()
    db.refresh(pkg_purchase)

    return pkg_purchase


def activate(purchase_id: UUID, company_id: UUID, db: Session) -> PackagePurchase:
    """Ativa a compra de pacote após pagamento confirmado.

    Numa única transação:
      PackagePurchase.status = ACTIVE
      PackagePurchase.activated_at = now()
      CustomerCredit criado (entitlement_type=PACKAGE, total_cotas=package.total_cotas)

    Após commit (best-effort):
      CommissionEngine.calculate_commission (PACKAGE_SOLD para seller se for Professional)
      EventBus.publish("package.purchased")
    """
    pkg_purchase = _get_purchase_or_404(purchase_id, company_id, db)

    if pkg_purchase.status == "ACTIVE":
        return pkg_purchase

    if pkg_purchase.status != "PENDING_PAYMENT":
        raise HTTPException(
            status_code=422,
            detail=f"Compra não está em PENDING_PAYMENT (status={pkg_purchase.status})",
        )

    package = pkg_purchase.package
    now = datetime.now(timezone.utc)
    expires_at = None
    if package.validity_days:
        expires_at = now + timedelta(days=package.validity_days)

    # Sprint 26: 1 CustomerCredit por item do pacote (com service_id/product_id persistidos)
    from app.infrastructure.db.models.customer_credit import CustomerCredit
    credits = []
    for item in package.items:
        credit = CustomerCredit(
            credit_id=uuid.uuid4(),
            company_id=company_id,
            customer_id=pkg_purchase.customer_id,
            entitlement_type="PACKAGE",
            source_id=purchase_id,
            service_id=item.service_id,
            product_id=item.product_id,
            total_cotas=item.quantity,
            remaining_cotas=item.quantity,
            status="ACTIVE",
            granted_at=now,
            expires_at=expires_at,
        )
        db.add(credit)
        credits.append(credit)

    pkg_purchase.status = "ACTIVE"
    pkg_purchase.activated_at = now

    db.commit()
    db.refresh(pkg_purchase)

    # Comissão PACKAGE_SOLD — best-effort, fora da transação
    _try_calculate_commission(pkg_purchase, package, company_id)

    # Evento best-effort
    _publish_purchased(pkg_purchase, credits)

    return pkg_purchase


def _try_calculate_commission(
    pkg_purchase: PackagePurchase,
    package: Package,
    company_id: UUID,
) -> None:
    """Calcula comissão PACKAGE_SOLD para seller_user_id se for Professional."""
    if not pkg_purchase.seller_user_id:
        return

    db2 = SessionLocal()
    try:
        set_rls_context(db2, company_id)

        professional_id = _resolve_professional_id(pkg_purchase.seller_user_id, company_id, db2)
        if not professional_id:
            return

        from app.modules.commission import service as commission_service
        commission_service.calculate_commission(
            professional_id=professional_id,
            service_id=None,  # pacote multi-item — sem serviço único (Sprint 26)
            gross_amount=Decimal(str(package.price)),
            provider_fee=Decimal("0"),
            operation_type="PACKAGE_SOLD",
            appointment_id=None,
            company_id=company_id,
            db=db2,
        )
    except Exception:
        logger.exception(
            "activate: erro ao calcular comissão PACKAGE_SOLD purchase_id=%s",
            pkg_purchase.purchase_id,
        )
        db2.rollback()
    finally:
        db2.close()


def _resolve_professional_id(
    seller_user_id: UUID,
    company_id: UUID,
    db: Session,
) -> Optional[UUID]:
    """Retorna professional_id se seller_user_id corresponder a um Professional ativo."""
    from app.infrastructure.db.models.professional import Professional
    prof = (
        db.query(Professional)
        .filter(
            Professional.company_id == company_id,
            Professional.id == seller_user_id,
        )
        .first()
    )
    if prof:
        return prof.id

    # Fallback: tenta encontrar Professional associado ao User via name match
    # Na realidade, o vínculo Professional↔User não está no schema atual.
    # A convenção do sprint é: seller_user_id IS a professional_id (mesmo UUID).
    # Se não encontrou, não há comissão.
    return None


def revoke_for_refund(payment_id: UUID, company_id: UUID, db: Session) -> None:
    """Chamado por payment.refunded — REVOCA crédito e REVERTE comissão.

    best-effort: exceções capturadas e logadas.
    """
    pkg_purchase = (
        db.query(PackagePurchase)
        .filter(
            PackagePurchase.company_id == company_id,
            PackagePurchase.payment_id == payment_id,
            PackagePurchase.status == "ACTIVE",
        )
        .first()
    )

    if not pkg_purchase:
        return

    # Revoga CustomerCredit via source_id=purchase_id
    from app.infrastructure.db.models.customer_credit import CustomerCredit
    credits = (
        db.query(CustomerCredit)
        .filter(
            CustomerCredit.company_id == company_id,
            CustomerCredit.source_id == pkg_purchase.purchase_id,
            CustomerCredit.status.in_(["ACTIVE", "EXHAUSTED"]),
        )
        .all()
    )
    for credit in credits:
        credit.status = "REVOKED"

    pkg_purchase.status = "REVOKED"

    # Reverte comissões PACKAGE_SOLD associadas
    _try_reverse_commissions(pkg_purchase, company_id, db)

    db.commit()


def _try_reverse_commissions(
    pkg_purchase: PackagePurchase,
    company_id: UUID,
    db: Session,
) -> None:
    from app.infrastructure.db.models.commission import Commission
    commissions = (
        db.query(Commission)
        .filter(
            Commission.company_id == company_id,
            Commission.operation_type == "PACKAGE_SOLD",
            Commission.status.in_(["CALCULATED", "DUE"]),
        )
        .all()
    )
    # Filtra as comissões do seller deste pacote (sem FK direta — usa professional_id e gross_amount)
    package_price = pkg_purchase.total_price
    seller_professional_id = None
    if pkg_purchase.seller_user_id:
        seller_professional_id = _resolve_professional_id(pkg_purchase.seller_user_id, company_id, db)

    for c in commissions:
        if seller_professional_id and c.professional_id != seller_professional_id:
            continue
        if c.gross_amount != package_price:
            continue
        c.status = "REVERSED"


def _publish_purchased(pkg_purchase: PackagePurchase, credits) -> None:
    try:
        from app.infrastructure.event_bus import DomainEvent, event_bus
        event_bus.publish(DomainEvent(
            event_id=uuid.uuid4(),
            event_type="package.purchased",
            occurred_at=datetime.now(timezone.utc),
            company_id=pkg_purchase.company_id,
            idempotency_key=f"package.purchased:{pkg_purchase.purchase_id}",
            actor={"type": "SYSTEM", "id": None},
            payload={
                "purchase_id": str(pkg_purchase.purchase_id),
                "package_id": str(pkg_purchase.package_id),
                "customer_id": str(pkg_purchase.customer_id),
                "credit_ids": [str(c.credit_id) for c in credits],
            },
        ))
    except Exception:
        pass


# ── CRUD Packages ─────────────────────────────────────────────────────────────

def list_packages(company_id: UUID, db: Session) -> List[Package]:
    packages = (
        db.query(Package)
        .filter(Package.company_id == company_id)
        .order_by(Package.created_at.desc())
        .all()
    )
    return _attach_item_names(db, packages)


def create_package(
    company_id: UUID,
    name: str,
    items: list,  # List[PackageItemCreate] — objetos com item_type/service_id/product_id/quantity
    price: Decimal,
    validity_days: Optional[int],
    db: Session,
) -> Package:
    """Cria Package + 1 PackageItem por item. total_cotas = sum(item.quantity)."""
    from app.infrastructure.db.models.package import PackageItem

    total_cotas = sum(item.quantity for item in items)
    pkg = Package(
        package_id=uuid.uuid4(),
        company_id=company_id,
        name=name,
        total_cotas=total_cotas,
        price=price,
        validity_days=validity_days,
        is_active=True,
    )
    db.add(pkg)
    db.flush()

    for order, item in enumerate(items):
        db.add(PackageItem(
            item_id=uuid.uuid4(),
            package_id=pkg.package_id,
            company_id=company_id,
            item_type=item.item_type,
            service_id=item.service_id,
            product_id=item.product_id,
            quantity=item.quantity,
            display_order=order,
        ))

    db.commit()
    db.refresh(pkg)
    return _attach_item_names(db, [pkg])[0]


def update_package(
    package_id: UUID,
    company_id: UUID,
    db: Session,
    **kwargs,
) -> Package:
    pkg = _get_package_or_404(package_id, company_id, db)
    allowed = {"name", "price", "validity_days", "is_active"}
    for k, v in kwargs.items():
        if k in allowed and v is not None:
            setattr(pkg, k, v)
    pkg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pkg)
    return _attach_item_names(db, [pkg])[0]


def delete_package(package_id: UUID, company_id: UUID, db: Session) -> Package:
    pkg = _get_package_or_404(package_id, company_id, db)
    pkg.is_active = False
    pkg.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(pkg)
    return _attach_item_names(db, [pkg])[0]


def _attach_item_names(db: Session, packages: List[Package]) -> List[Package]:
    """Resolve service_name/product_name de cada item (batch, sem N+1) e os
    anexa como atributos transientes — Pydantic from_attributes os serializa."""
    from app.infrastructure.db.models.product import Product
    from app.infrastructure.db.models.service import Service

    service_ids, product_ids = set(), set()
    for pkg in packages:
        for item in pkg.items:
            if item.service_id:
                service_ids.add(item.service_id)
            if item.product_id:
                product_ids.add(item.product_id)

    svc_names = {}
    if service_ids:
        svc_names = {
            s.id: s.name
            for s in db.query(Service).filter(Service.id.in_(service_ids)).all()
        }
    prod_names = {}
    if product_ids:
        prod_names = {
            p.id: p.name
            for p in db.query(Product).filter(Product.id.in_(product_ids)).all()
        }

    for pkg in packages:
        for item in pkg.items:
            item.service_name = svc_names.get(item.service_id)
            item.product_name = prod_names.get(item.product_id)
    return packages


def list_purchases(
    company_id: UUID,
    db: Session,
    customer_id: Optional[UUID] = None,
    status: Optional[str] = None,
) -> List[PackagePurchase]:
    q = db.query(PackagePurchase).filter(PackagePurchase.company_id == company_id)
    if customer_id:
        q = q.filter(PackagePurchase.customer_id == customer_id)
    if status:
        q = q.filter(PackagePurchase.status == status)
    return q.order_by(PackagePurchase.created_at.desc()).all()


def get_purchase(purchase_id: UUID, company_id: UUID, db: Session) -> PackagePurchase:
    return _get_purchase_or_404(purchase_id, company_id, db)


# ── Helpers internos ──────────────────────────────────────────────────────────

def _get_package_or_404(package_id: UUID, company_id: UUID, db: Session) -> Package:
    pkg = (
        db.query(Package)
        .filter(Package.package_id == package_id, Package.company_id == company_id)
        .first()
    )
    if not pkg:
        raise HTTPException(status_code=404, detail="Pacote não encontrado")
    return pkg


def _get_purchase_or_404(purchase_id: UUID, company_id: UUID, db: Session) -> PackagePurchase:
    purchase = (
        db.query(PackagePurchase)
        .filter(PackagePurchase.purchase_id == purchase_id, PackagePurchase.company_id == company_id)
        .first()
    )
    if not purchase:
        raise HTTPException(status_code=404, detail="Compra de pacote não encontrada")
    return purchase
