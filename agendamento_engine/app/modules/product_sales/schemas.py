from decimal import Decimal

from pydantic import BaseModel


class PendingProductItem(BaseModel):
    product_name: str
    quantity: int
    status: str  # RESERVED (pagar + retirar) | PURCHASED (pago, só retirar)
    total_price: Decimal


class PendingProductsResponse(BaseModel):
    has_pending: bool
    items: list[PendingProductItem] = []
