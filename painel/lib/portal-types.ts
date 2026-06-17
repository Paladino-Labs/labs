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
  company_name?: string // gap #1 — ver acima
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
  company_name?: string // gap #1
  entitlement_type: string // gap #2 — sem nome de serviço/pacote
  total_cotas: number
  remaining_cotas: number
  status: string
  granted_at: string | null
  expires_at: string | null
}

export interface PortalSubscriptionItem {
  subscription_id: string
  company_id: string
  company_name?: string // gap #1
  plan_name: string | null
  status: string
  next_billing_at: string | null
  paused_at: string | null
  cancelled_at: string | null
  // valor do plano não vem no serializer atual — opcional/forward-compatible
  amount?: string | null
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

/** Rótulo do estabelecimento — fallback enquanto o backend não serializa o nome (gap #1). */
export function establishmentLabel(item: { company_name?: string }): string {
  return item.company_name ?? "Estabelecimento"
}
