import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  APPOINTMENT_STATUS_LABELS,
  CUSTOMER_CREDIT_STATUS_LABELS,
  SUBSCRIPTION_STATUS_LABELS,
} from "@/lib/constants"

// Tom verde de "sucesso" — não há token semântico de sucesso no design system;
// segue o precedente do uso de amber-* hardcoded na superfície /manage (Fase 5A).
const SUCCESS_CLASS =
  "border-transparent bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400"
const PAUSED_CLASS =
  "border-transparent bg-amber-500/10 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400"

export function AppointmentStatusBadge({ status }: { status: string }) {
  const label = APPOINTMENT_STATUS_LABELS[status] ?? status
  if (status === "COMPLETED") return <Badge className={SUCCESS_CLASS}>{label}</Badge>
  if (status === "CANCELLED" || status === "NO_SHOW" || status === "FAILED")
    return <Badge variant="destructive">{label}</Badge>
  if (status === "SCHEDULED") return <Badge>{label}</Badge>
  return <Badge variant="secondary">{label}</Badge>
}

// Redesign F3 — status de Payment (PENDING → CONFIRMED → REFUNDED | FAILED | CANCELLED).
// Rótulos voltados ao cliente: CONFIRMED = "Pago" (não "Confirmado" do painel tenant).
const PAYMENT_STATUS_LABELS: Record<string, string> = {
  PENDING:   "Pendente",
  CONFIRMED: "Pago",
  REFUNDED:  "Estornado",
  FAILED:    "Falhou",
  CANCELLED: "Cancelado",
}

export function PaymentStatusBadge({ status }: { status: string }) {
  const label = PAYMENT_STATUS_LABELS[status] ?? status
  if (status === "CONFIRMED") return <Badge className={SUCCESS_CLASS}>{label}</Badge>
  if (status === "PENDING") return <Badge className={PAUSED_CLASS}>{label}</Badge>
  if (status === "FAILED") return <Badge variant="destructive">{label}</Badge>
  return <Badge variant="secondary">{label}</Badge>
}

export function CreditStatusBadge({ status }: { status: string }) {
  const label = CUSTOMER_CREDIT_STATUS_LABELS[status] ?? status
  if (status === "ACTIVE") return <Badge className={SUCCESS_CLASS}>{label}</Badge>
  if (status === "EXPIRED" || status === "REVOKED")
    return <Badge variant="destructive">{label}</Badge>
  return <Badge variant="secondary">{label}</Badge>
}

export function SubscriptionStatusBadge({ status }: { status: string }) {
  const label = SUBSCRIPTION_STATUS_LABELS[status] ?? status
  if (status === "ACTIVE") return <Badge className={cn(SUCCESS_CLASS)}>{label}</Badge>
  if (status === "PAUSED") return <Badge className={PAUSED_CLASS}>{label}</Badge>
  if (status === "CANCELLED" || status === "SUSPENDED")
    return <Badge variant="destructive">{label}</Badge>
  if (status === "OVERDUE") return <Badge className={PAUSED_CLASS}>{label}</Badge>
  return <Badge variant="secondary">{label}</Badge>
}
