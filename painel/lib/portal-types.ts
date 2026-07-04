// Tipos do Portal do Cliente (Fase 5B).
//
// ⚠️ Vários GETs do portal declaram `schema: {}` no OpenAPI (dict não tipado).
// Os tipos abaixo refletem o que `app/modules/portal/service.py` realmente
// serializa (conferido no backend), NÃO o contrato OpenAPI.
//
// GAPS DOCUMENTADOS (backend pendente — não inventar dados):
//  1. Os itens só trazem `company_id` (UUID), NÃO o nome do estabelecimento.
//     `company_name?` abaixo é OPCIONAL e forward-compatible: hoje vem
//     undefined → UI cai no rótulo "Estabelecimento". Quando o backend
//     adicionar o nome aos serializers, a UI passa a exibi-lo sem mudança.
//  2. `credit` não traz nome de serviço/pacote (só `entitlement_type`).
//  3. Não existe endpoint de histórico de consumo de cota → card expansível
//     mostra "Em breve".

export interface PortalAppointmentItem {
  id: string
  company_id: string
  company_name: string | null // B1 — serializado pelo backend (fallback "Estabelecimento")
  start_at: string
  end_at: string
  status: string
  service_names: string[]
  professional_name: string | null
  total_amount: string
}

export interface PortalCreditItem {
  credit_id: string
  company_id: string
  company_name: string | null // B1 — serializado pelo backend
  entitlement_type: string
  service_name: string | null // B2 — nome do serviço/pacote (fallback entitlement_type)
  total_cotas: number
  remaining_cotas: number
  status: string
  granted_at: string | null
  expires_at: string | null
}

export interface PortalSubscriptionItem {
  subscription_id: string
  company_id: string
  company_name: string | null // B1 — serializado pelo backend
  plan_name: string | null
  status: string
  next_billing_at: string | null
  paused_at: string | null
  cancelled_at: string | null
  // valor do plano não vem no serializer atual — opcional/forward-compatible
  amount?: string | null
}

// B3 — histórico de consumo de cota (GET /portal/credits/{id}/consumptions)
export interface CreditConsumptionItem {
  occurred_at: string // ISO date-time
  appointment_id: string | null
  service_name: string | null
  professional_name: string | null
  quantity_used: number
}

// B6 — produto público da vitrine (GET /booking/{slug}/products)
export interface PublicProduct {
  id: string
  name: string
  description: string | null
  price: string // Decimal-string ("49.90") — usar formatBRLFromDecimal
  image_url: string | null
  available: boolean
}

// Fase 1 — catálogo público da vitrine (/book/[slug])

export interface PublicPackageItem {
  item_type:    "SERVICE" | "PRODUCT"
  service_name: string | null
  product_name: string | null
  quantity:     number
}

export interface PublicPackage {
  package_id:    string
  name:          string
  items:         PublicPackageItem[]
  total_cotas:   number
  price:         string          // Decimal-string → formatBRLFromDecimal
  validity_days: number | null
}

export interface PublicPlanItem {
  item_type:    "SERVICE" | "PRODUCT"
  service_name: string | null
  product_name: string | null
  quantity:     number
}

export interface PublicPlan {
  plan_id:               string
  name:                  string
  items:                 PublicPlanItem[]
  total_cotas_per_cycle: number           // NÃO cotas_per_cycle (campo antigo removido)
  price:                 string           // Decimal-string → formatBRLFromDecimal
  cycle_days:            number
  rollover_enabled:      boolean
}

export interface PublicPromotion {
  promotion_id:   string
  name:           string
  description:    string | null
  discount_type:  string          // "PERCENTAGE" | "FIXED_AMOUNT" | "OVERRIDE_PRICE" | "FREE_ITEM"
  discount_value: string | null   // Decimal-string | null → formatBRLFromDecimal
  valid_until:    string | null   // ISO datetime | null
}

// Fase 2 — checkout unificado público (POST /booking/{slug}/checkout)

export interface CheckoutAppointmentResult {
  appointment_id:    string
  service_name:      string
  professional_name: string
  start_at:          string
  total_amount:      string
  manage_url:        string | null
}
export interface CheckoutPurchaseResult {
  purchase_id:  string
  package_name: string
  total_cotas:  number
  amount_paid:  string
}
export interface CheckoutSubscriptionResult {
  subscription_id: string
  plan_name:       string
  next_billing_at: string
  amount_paid:     string
}
export interface CheckoutProductResult {
  product_name: string
  quantity:     number
  amount_paid:  string
}
export interface CheckoutResponse {
  customer_id:    string
  appointments:   CheckoutAppointmentResult[]
  purchases:      CheckoutPurchaseResult[]
  subscriptions:  CheckoutSubscriptionResult[]
  product_sales:  CheckoutProductResult[]
  coupon_applied: string | null
  discount_amount: string | null
  total_charged:  string
  warnings:       string[]
}

// Redesign F1 — cupons do cliente (GET /portal/coupons; lista plana).
// discount_type/discount_value vêm da Promotion pai — podem ser null se a
// promoção não existir mais (serializer usa `promo.discount_type if promo`).
export interface PortalCouponItem {
  coupon_id:      string
  code:           string
  company_name:   string | null
  discount_type:  string          // PERCENTAGE | FIXED_AMOUNT | ...
  discount_value: string | null   // Decimal-string | null
  valid_until:    string | null   // ISO | null
  is_personal:    boolean
}

// Redesign F1 — vendas de produto (GET /portal/product-sales?status=).
export interface PortalProductSaleItem {
  sale_id:      string
  company_name: string | null
  product_id:   string
  product_name: string
  quantity:     number
  unit_price:   string   // Decimal-string
  total_price:  string   // Decimal-string
  status:       string   // RESERVED | PURCHASED | PICKED_UP
  created_at:   string   // ISO
  picked_up_at: string | null
}

export interface PortalProductSalesResponse {
  items:     PortalProductSaleItem[]
  page:      number
  page_size: number
  total:     number
}

// Redesign F3 — histórico de pagamentos (GET /portal/payments?page=&page_size=).
// Shape conferido em modules/portal/service.get_payments. Não há campo de
// descrição semântica — só company_name/método/datas/cupom.
export interface PortalPaymentItem {
  payment_id:     string
  company_name:   string | null
  amount:         string   // Decimal-string (net_charged_amount)
  payment_method: string   // cru: CASH | CHAVE_PIX | MAQUININHA | PIX | ... (Payment.payment_method)
  status:         string   // cru: PENDING | CONFIRMED | REFUNDED | FAILED | CANCELLED
  paid_at:        string | null   // ISO | null
  created_at:     string          // ISO
  coupon_code:    string | null
}

export interface PortalPaymentsResponse {
  items:     PortalPaymentItem[]
  page:      number
  page_size: number
  total:     number
}

// Redesign F2 — detalhe de agendamento (GET /portal/appointments/{id}).
// Shape conferido em modules/portal/service.get_appointment_detail.
export interface PortalAppointmentServiceItem {
  service_name:     string
  duration_minutes: number
  price:            string   // Decimal-string
}

export interface PortalAppointmentDetail {
  appointment_id:    string
  company_name:      string | null
  company_address:   string | null
  company_city:      string | null
  company_maps_url:  string | null
  company_whatsapp:  string | null
  company_timezone:  string
  professional_name: string | null
  services:          PortalAppointmentServiceItem[]
  start_at:          string   // ISO
  end_at:            string   // ISO
  status:            string
  total_amount:      string   // Decimal-string
  can_cancel:        boolean
  can_reschedule:    boolean
}

export interface PortalCancelResult {
  appointment_id:   string
  status:           string
  deposit_retained: boolean
}

export interface PortalRescheduleResult {
  appointment_id: string
  status:         string
  start_at:       string   // ISO
}

export interface PortalDashboardResponse {
  upcoming_appointments: PortalAppointmentItem[]
  active_credits: PortalCreditItem[]
  active_subscriptions: PortalSubscriptionItem[]
}

export interface PortalHistoryResponse {
  items: PortalAppointmentItem[]
  page: number
  page_size: number
  total: number
}

export interface PortalPaymentSourceItem {
  id: string
  company_id: string
  provider: string
  mode: string
  last_four: string | null
  brand: string | null
  granted_at: string | null
  revoked_at: string | null
}

// Tipado no OpenAPI (ConsentRecordResponse). status ∈ GRANTED|REVOKED.
export interface PortalConsentRecord {
  id: string
  identity_id: string
  company_id: string | null
  consent_type: string
  channel: string | null
  status: string
  source_channel: string
  occurred_at: string
  notes: string | null
}

// IdentityResponse (tipado).
export interface PortalIdentity {
  id: string
  phone_e164: string
  phone_national_normalized: string
  name: string | null
  email: string | null
  cpf_masked: string | null
}

export interface PortalTokenResponse {
  access_token: string
  token_type: string
}

/** Rótulo do estabelecimento — usa company_name (B1); fallback "Estabelecimento". */
export function establishmentLabel(item: { company_name?: string | null }): string {
  return item.company_name ?? "Estabelecimento"
}
