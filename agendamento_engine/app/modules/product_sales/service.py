from uuid import UUID

from sqlalchemy.orm import Session

from app.infrastructure.db.models.product_sale import ProductSale


def get_pending_pickups(
    db: Session, customer_id: UUID, company_id: UUID
) -> list[ProductSale]:
    """
    Produtos que o cliente comprou e ainda não retirou, naquela empresa.
    Pendência = RESERVED (pagar+retirar no local) ou PURCHASED (pago
    online, aguardando retirada). PICKED_UP não é pendência.
    """
    return (
        db.query(ProductSale)
        .filter(
            ProductSale.customer_id == customer_id,
            ProductSale.company_id == company_id,
            ProductSale.status.in_(["RESERVED", "PURCHASED"]),
        )
        .order_by(ProductSale.created_at.asc())
        .all()
    )
