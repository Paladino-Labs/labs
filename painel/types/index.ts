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
