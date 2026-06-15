export interface Professional {
  id: string
  company_id: string
  name: string
  specialty?: string | null
  active: boolean
  work_start?: string
  work_end?: string
  working_days?: number[]
  commission_rate?: number
  specialties?: string[]
  cpf_cnpj_masked?: string
}

export interface Service {
  id: string
  company_id: string
  name: string
  price: string
  duration: number
  active: boolean
  description?: string
  image_url?: string
}

export interface Customer {
  id: string
  company_id: string
  name: string
  phone: string
  email?: string
  notes?: string
  active: boolean
}

export interface CustomerAppointmentItem {
  id: string
  start_at: string
  end_at: string
  status: string
  service_names: string[]
  professional_name?: string
  total_amount: string
}

export interface Product {
  id: string
  company_id: string
  name: string
  price: string
  stock: number
  description?: string
  image_url?: string
  active: boolean
}

export interface User {
  id: string
  company_id: string
  email: string
  role: string
  active: boolean
}

export interface AppointmentServiceSnapshot {
  id: string
  service_id: string
  service_name: string
  duration_snapshot: string
  price_snapshot: string
}

export interface Appointment {
  id: string
  company_id: string
  professional_id: string
  client_id: string
  start_at: string
  end_at: string
  status: string
  financial_status: string
  subtotal_amount: string
  discount_amount?: string
  total_amount: string
  services: AppointmentServiceSnapshot[]
  professional?: { id: string; name: string }
  customer?: { id: string; name: string; phone: string }
}

export interface WorkingHour {
  id: string
  professional_id: string
  weekday: number        // 0 = Segunda … 6 = Domingo
  opening_time: string   // "HH:MM:SS"
  closing_time: string   // "HH:MM:SS"
  is_active: boolean
}

export interface ScheduleBlock {
  id: string
  professional_id: string
  start_at: string
  end_at: string
  reason?: string
}

export interface ProfessionalService {
  id: string
  service_id: string
  service_name: string
  price: string
  duration: number
  commission_percentage?: string
}

/* ============================ Fase 2 — Comercial ============================ */

export interface Category {
  category_id: string
  company_id: string
  name: string
  entity_type: string
  is_default: boolean
  is_active: boolean
  sort_order: number
}

export interface ServiceVariant {
  variant_id: string
  service_id: string
  company_id: string
  name: string
  price: string
  duration_min: number
  is_active: boolean
  sort_order: number
}

export interface PricingOverride {
  override_id: string
  professional_id: string
  service_id: string
  company_id: string
  price: string
  duration_min?: number | null
  is_active: boolean
}

export interface Package {
  package_id: string
  company_id: string
  name: string
  service_id?: string | null
  total_cotas: number
  price: string
  validity_days?: number | null
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export interface PackagePurchase {
  purchase_id: string
  company_id: string
  customer_id: string
  package_id: string
  seller_user_id?: string | null
  payment_id?: string | null
  total_price: string
  status: string
  activated_at?: string | null
  created_at: string
}

export interface SubscriptionPlan {
  plan_id: string
  company_id: string
  name: string
  service_id?: string | null
  cotas_per_cycle: number
  price: string
  cycle_days: number
  rollover_enabled: boolean
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export interface Subscription {
  subscription_id: string
  company_id: string
  customer_id: string
  plan_id: string
  status: string
  next_billing_at?: string | null
  overdue_since?: string | null
  paused_at?: string | null
  cancelled_at?: string | null
  created_at: string
}

export interface Promotion {
  id: string
  company_id: string
  name: string
  description?: string | null
  discount_type: string
  discount_value?: string | null
  application_mode: string
  cumulative: boolean
  priority: number
  status: string
  valid_from?: string | null
  valid_until?: string | null
  max_uses?: number | null
  max_uses_per_customer?: number | null
  uses_count: number
  conditions?: Record<string, unknown> | null
  created_by?: string | null
  created_at: string
  updated_at?: string | null
}

export interface Coupon {
  id: string
  company_id: string
  promotion_id: string
  code: string
  generation_type: string
  max_uses?: number | null
  uses_count: number
  coupon_reopen_policy: string
  status: string
  customer_id?: string | null
  expires_at?: string | null
}

/* ====================== Fase 3 — Financeiro profundo ====================== */

export interface RecurrenceRule {
  frequency: string
  day_of_month: number
  end_date?: string | null
}

export interface Expense {
  id: string
  company_id: string
  description: string
  amount: string
  category: string
  supplier_id?: string | null
  due_date: string
  status: string                       // PENDENTE | PAGA | CANCELLED
  paid_at?: string | null
  paid_amount?: string | null
  recurrence_rule?: RecurrenceRule | null
  parent_expense_id?: string | null
  created_by?: string | null
  created_at: string
}

export interface StockProduct {
  id: string
  name: string
  active: boolean
  stock?: number | null
  stock_min_alert?: string | null
  unit?: string | null
  avg_cost?: string | null
}

export interface StockMovement {
  id: string
  company_id: string
  product_id: string
  movement_type: string                // ENTRADA | VENDA | USO_INTERNO | PERDA | AJUSTE
  quantity: string
  unit_cost?: string | null
  source_type?: string | null
  source_id?: string | null
  notes?: string | null
  occurred_at: string
  created_by?: string | null
}

export interface Supplier {
  id: string
  company_id: string
  name: string
  contact?: string | null
  document?: string | null
  active: boolean
  created_at: string
  updated_at?: string | null
}

export interface Payable {
  id: string
  company_id: string
  supplier_id?: string | null
  description: string
  total_amount: string
  paid_amount: string
  status: string                       // OPEN | PARTIALLY_PAID | PAID | CANCELLED
  due_date?: string | null
  closing_method: string
  source_type: string
  source_id?: string | null
  created_at: string
  updated_at?: string | null
}

export interface PayableInstallment {
  id: string
  payable_id: string
  amount: string
  due_date?: string | null
  paid_at?: string | null
  payment_id?: string | null
  installment_number: number
  status: string                       // OPEN | PAID
}

export interface FinancialAccount {
  account_id: string
  company_id: string
  name: string
  type: string                         // CAIXA | ACQUIRER | BANK | ESCROW
  provider?: string | null
  external_ref?: string | null
  currency: string
  status: string                       // ACTIVE
  is_default_inflow: boolean
  created_at: string
  updated_at?: string | null
}

export interface FinancialMovement {
  movement_id: string
  company_id: string
  account_id: string
  type: string                         // INFLOW | OUTFLOW | TRANSFER_IN | TRANSFER_OUT
  amount: string
  occurred_at: string
  source_type: string
  source_id: string
  transfer_id?: string | null
  created_at: string
}

export interface Transfer {
  transfer_id: string
  company_id: string
  from_account_id: string
  to_account_id: string
  amount: string
  status: string                       // REQUESTED | COMPLETED | FAILED
  requested_at: string
  completed_at?: string | null
  failed_at?: string | null
  failure_reason?: string | null
  notes?: string | null
}

export interface Reconciliation {
  reconciliation_id: string
  company_id: string
  account_id: string
  status: string                       // OPEN | CLOSED
  opened_at: string
  closed_at?: string | null
  opened_by?: string | null
  closed_by?: string | null
  notes?: string | null
}

export interface CashCount {
  cash_count_id: string
  company_id: string
  account_id: string
  expected_amount: string
  counted_amount: string
  discrepancy: string
  resolution: string                   // ADJUSTED | NO_ADJUSTMENT
  notes?: string | null
  entry_id?: string | null
  created_by?: string | null
  created_at: string
}

export interface StatementEntry {
  id: string
  company_id: string
  account_id: string
  occurred_at: string
  amount: string
  direction: string                    // INFLOW | OUTFLOW
  description?: string | null
  status: string                       // PENDING | MATCHED | DISMISSED
  matched_movement_id?: string | null
  dismissed_reason?: string | null
  dismissed_at?: string | null
  dismissed_by?: string | null
  imported_at?: string | null
  import_batch_id: string
}

export interface StatementBatch {
  batch_id: string
  account_id: string
  imported_at?: string | null
  total: number
  matched: number
  pending: number
  dismissed: number
}

export interface DreResponse {
  date_from: string
  date_to: string
  receita: Record<string, string>
  receita_total: string
  custo: Record<string, string>
  custo_total: string
  despesa: Record<string, string>
  despesa_total: string
  taxa: Record<string, string>
  taxa_total: string
  comissao: Record<string, string>
  comissao_total: string
  estorno: Record<string, string>
  estorno_total: string
  ajuste: Record<string, string>
  ajuste_total: string
  resultado_bruto: string
  resultado_liquido: string
}

export interface FinancialSettings {
  payment_provider?: string | null
  external_account_id?: string | null
  external_account_status?: string | null
  external_account_created_at?: string | null
  accounts_count: number
}
