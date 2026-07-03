"""
Schemas HTTP do checkout unificado público — Sprint B2.

Endpoints públicos (prefixo /booking/{slug}):
  GET  /packages              → PublicPackageOut[]
  GET  /subscription-plans    → PublicPlanOut[]
  GET  /promotions            → PublicPromotionOut[]
  POST /coupon/validate       → CouponValidateResponse
  POST /checkout              → CheckoutResponse

Convenção de dinheiro: Decimal serializado como string (str(value)), mesmo
padrão dos demais schemas de booking.
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


# ── Respostas de catálogo ──────────────────────────────────────────────────

class PublicPackageItemOut(BaseModel):
    item_type:    str
    service_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity:     int


class PublicPackageOut(BaseModel):
    package_id:    UUID
    name:          str
    items:         list[PublicPackageItemOut]
    total_cotas:   int
    price:         str
    validity_days: Optional[int] = None


class PublicPlanItemOut(BaseModel):
    item_type:    str
    service_name: Optional[str] = None
    product_name: Optional[str] = None
    quantity:     int


class PublicPlanOut(BaseModel):
    plan_id:               UUID
    name:                  str
    items:                 list[PublicPlanItemOut]
    total_cotas_per_cycle: int
    price:                 str
    cycle_days:            int
    rollover_enabled:      bool


class PublicPromotionOut(BaseModel):
    promotion_id:   UUID
    name:           str
    description:    Optional[str] = None
    discount_type:  str
    discount_value: Optional[str] = None
    valid_until:    Optional[datetime] = None


# ── Validação de cupom ─────────────────────────────────────────────────────

class CouponValidateRequest(BaseModel):
    coupon_code:  str
    gross_amount: str
    service_ids:  list[UUID] = []
    product_ids:  list[UUID] = []


class CouponValidateResponse(BaseModel):
    valid:          bool
    discount_type:  Optional[str] = None
    discount_value: Optional[str] = None
    net_amount:     Optional[str] = None
    description:    Optional[str] = None
    error:          Optional[str] = None


# ── Checkout unificado ─────────────────────────────────────────────────────

class CheckoutServiceItem(BaseModel):
    professional_id: UUID
    service_id:      UUID
    start_at:        datetime
    end_at:          datetime


class CheckoutProductItem(BaseModel):
    product_id: UUID
    quantity:   int = 1


class CheckoutPackageItem(BaseModel):
    package_id:     UUID
    payment_method: str = "CASH"


class CheckoutSubscriptionItem(BaseModel):
    plan_id:        UUID
    payment_method: str = "CASH"


class CheckoutRequest(BaseModel):
    # Opcionais desde Portal Camada 2: com JWT portal, o cliente vem da
    # identity; anônimo exige ambos (422 explícito no endpoint).
    customer_name:   Optional[str] = None
    customer_phone:  Optional[str] = None
    services:        list[CheckoutServiceItem]      = []
    products:        list[CheckoutProductItem]      = []
    packages:        list[CheckoutPackageItem]      = []
    subscriptions:   list[CheckoutSubscriptionItem] = []
    coupon_code:     Optional[str]                  = None
    idempotency_key: Optional[UUID]                 = None


class CheckoutAppointmentResult(BaseModel):
    appointment_id:    UUID
    service_name:      str
    professional_name: str
    start_at:          datetime
    total_amount:      str
    manage_url:        Optional[str] = None


class CheckoutPurchaseResult(BaseModel):
    purchase_id:  UUID
    package_name: str
    total_cotas:  int
    amount_paid:  str


class CheckoutSubscriptionResult(BaseModel):
    subscription_id: UUID
    plan_name:       str
    next_billing_at: datetime
    amount_paid:     str


class CheckoutProductResult(BaseModel):
    product_name: str
    quantity:     int
    amount_paid:  str


class CheckoutResponse(BaseModel):
    customer_id:     UUID
    appointments:    list[CheckoutAppointmentResult]   = []
    purchases:       list[CheckoutPurchaseResult]      = []
    subscriptions:   list[CheckoutSubscriptionResult]  = []
    product_sales:   list[CheckoutProductResult]       = []
    coupon_applied:  Optional[str] = None
    discount_amount: Optional[str] = None
    total_charged:   str
    warnings:        list[str] = []
