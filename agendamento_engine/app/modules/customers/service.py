import re
from typing import Optional
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models import Customer
from app.modules.customers.schemas import CustomerCreate, CustomerUpdate


def normalize_phone(phone: str) -> str:
    """
    Normaliza número de telefone para E.164 sem o prefixo '+'.
    Ex: "(11) 99999-9999" → "5511999999999"
        "+5511999999999"  → "5511999999999"
        "11999999999"     → "5511999999999"
    """
    digits = re.sub(r"\D", "", phone)
    # Adiciona DDI 55 (Brasil) se não tiver
    if not digits.startswith("55") and len(digits) <= 11:
        digits = "55" + digits
    return digits


def list_customers(db: Session, company_id: UUID):
    return (
        db.query(Customer)
        .filter(Customer.company_id == company_id, Customer.active == True)
        .order_by(Customer.name)
        .all()
    )


def get_customer_or_404(db: Session, company_id: UUID, customer_id: UUID) -> Customer:
    c = db.query(Customer).filter(
        Customer.id == customer_id,
        Customer.company_id == company_id,
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return c


def create_customer(db: Session, company_id: UUID, data: CustomerCreate) -> Customer:
    existing = db.query(Customer).filter(
        Customer.phone == data.phone,
        Customer.company_id == company_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Telefone já cadastrado para outro cliente")

    customer = Customer(company_id=company_id, **data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def get_by_phone(db: Session, company_id: UUID, phone: str) -> Optional[Customer]:
    """
    Busca cliente pelo número de telefone normalizado.
    Usado pelo bot para identificar clientes via WhatsApp.
    """
    normalized = normalize_phone(phone)
    return db.query(Customer).filter(
        Customer.company_id == company_id,
        Customer.phone == normalized,
        Customer.active == True,
    ).first()


def get_or_create_by_phone(
    db: Session, company_id: UUID, phone: str, name: str
) -> Customer:
    """
    Retorna o cliente existente ou cria um novo com os dados mínimos.
    Usado pelo bot no fluxo de cadastro de novo cliente.
    """
    customer = get_by_phone(db, company_id, phone)
    if customer:
        return customer
    normalized = normalize_phone(phone)
    customer = Customer(company_id=company_id, name=name, phone=normalized)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(db: Session, company_id: UUID, customer_id: UUID, data: CustomerUpdate) -> Customer:
    customer = get_customer_or_404(db, company_id, customer_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(customer, field, value)
    db.commit()
    db.refresh(customer)
    return customer
