export interface Professional {
  id: string
  company_id: string
  name: string
  active: boolean
}

export interface Service {
  id: string
  company_id: string
  name: string
  price: string
  duration: number
  active: boolean
}

export interface Customer {
  id: string
  company_id: string
  name: string
  phone: string
  email?: string
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
