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
