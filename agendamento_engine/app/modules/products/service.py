from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.infrastructure.db.models.product import Product
from app.modules.products.schemas import ProductCreate, ProductUpdate


def list_products(db: Session, company_id: UUID, active_only: bool = True):
    q = db.query(Product).filter(Product.company_id == company_id)
    if active_only:
        q = q.filter(Product.active == True)
    return q.order_by(Product.name).all()


def get_product_or_404(db: Session, company_id: UUID, product_id: UUID) -> Product:
    p = db.query(Product).filter(
        Product.id == product_id,
        Product.company_id == company_id,
    ).first()
    if not p:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    return p


def create_product(db: Session, company_id: UUID, data: ProductCreate) -> Product:
    p = Product(company_id=company_id, **data.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def update_product(db: Session, company_id: UUID, product_id: UUID, data: ProductUpdate) -> Product:
    p = get_product_or_404(db, company_id, product_id)
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return p
