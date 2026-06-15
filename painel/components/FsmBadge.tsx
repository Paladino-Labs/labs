import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"
import {
  APPOINTMENT_STATUS_LABELS,
  EXPENSE_STATUS_LABELS,
  PAYABLE_STATUS_LABELS,
  INSTALLMENT_STATUS_LABELS,
  RECONCILIATION_STATUS_LABELS,
  STATEMENT_STATUS_LABELS,
  TRANSFER_STATUS_LABELS,
  NPS_SURVEY_STATUS_LABELS,
  COMMUNICATION_LOG_STATUS_LABELS,
} from "@/lib/constants"

/* ============================ Appointment FSM ============================ */

const APPT_CLASS: Record<string, string> = {
  DRAFT:       "bg-muted text-muted-foreground border-border",
  REQUESTED:   "bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300",
  SCHEDULED:   "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  IN_PROGRESS: "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  COMPLETED:   "bg-muted text-muted-foreground border-border",
  CANCELLED:   "bg-destructive/15 text-destructive border-destructive/30",
  NO_SHOW:     "bg-destructive/15 text-destructive border-destructive/30",
  FAILED:      "bg-destructive/15 text-destructive border-destructive/30",
}

export function AppointmentBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", APPT_CLASS[status])}>
      {APPOINTMENT_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ============================== Payment FSM ============================== */

const PAY_LABEL: Record<string, string> = {
  PENDING:   "Pendente",
  CONFIRMED: "Confirmado",
  REFUNDED:  "Estornado",
  FAILED:    "Falhou",
  CANCELLED: "Cancelado",
}

const PAY_CLASS: Record<string, string> = {
  PENDING:   "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  CONFIRMED: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  REFUNDED:  "bg-muted text-muted-foreground border-border",
  FAILED:    "bg-destructive/15 text-destructive border-destructive/30",
  CANCELLED: "bg-muted text-muted-foreground border-border",
}

export function PaymentBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", PAY_CLASS[status])}>
      {PAY_LABEL[status] ?? status}
    </Badge>
  )
}

/* ============================ CRM Classification ============================ */

const CRM_LABEL: Record<string, string> = {
  NOVO:       "Novo",
  FREQUENTE:  "Frequente",
  VIP:        "VIP",
  EM_RISCO:   "Em risco",
  RECUPERADO: "Recuperado",
  REGULAR:    "Regular",
}

const CRM_CLASS: Record<string, string> = {
  NOVO:       "bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300",
  FREQUENTE:  "bg-primary/10 text-primary border-primary/30",
  VIP:        "bg-sidebar-primary/15 text-sidebar-primary border-sidebar-primary/40",
  EM_RISCO:   "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
  RECUPERADO: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  REGULAR:    "bg-muted text-muted-foreground border-border",
}

export function CrmBadge({ classification }: { classification: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", CRM_CLASS[classification])}>
      {CRM_LABEL[classification] ?? classification}
    </Badge>
  )
}

/* ====================== Fase 2 — FSMs do Comercial ====================== */

const EMERALD = "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300"
const AMBER = "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300"
const DESTRUCTIVE = "bg-destructive/15 text-destructive border-destructive/30"
const NEUTRAL = "bg-muted text-muted-foreground border-border"

/* --------------------------- PackagePurchase --------------------------- */

const PKG_PURCHASE_LABEL: Record<string, string> = {
  PENDING_PAYMENT: "Pagamento pendente",
  ACTIVE:          "Ativo",
  REVOKED:         "Revogado",
}

const PKG_PURCHASE_CLASS: Record<string, string> = {
  PENDING_PAYMENT: AMBER,
  ACTIVE:          EMERALD,
  REVOKED:         DESTRUCTIVE,
}

export function PackagePurchaseBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", PKG_PURCHASE_CLASS[status])}>
      {PKG_PURCHASE_LABEL[status] ?? status}
    </Badge>
  )
}

/* ------------------------------ Subscription ------------------------------ */

const SUBSCRIPTION_LABEL: Record<string, string> = {
  ACTIVE:    "Ativa",
  PAUSED:    "Pausada",
  OVERDUE:   "Em atraso",
  SUSPENDED: "Suspensa",
  CANCELLED: "Cancelada",
}

const SUBSCRIPTION_CLASS: Record<string, string> = {
  ACTIVE:    EMERALD,
  PAUSED:    AMBER,
  OVERDUE:   AMBER,
  SUSPENDED: DESTRUCTIVE,
  CANCELLED: NEUTRAL,
}

export function SubscriptionBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", SUBSCRIPTION_CLASS[status])}>
      {SUBSCRIPTION_LABEL[status] ?? status}
    </Badge>
  )
}

/* ------------------------------- Promotion ------------------------------- */

const PROMOTION_LABEL: Record<string, string> = {
  DRAFT:     "Rascunho",
  ACTIVE:    "Ativa",
  PAUSED:    "Pausada",
  EXPIRED:   "Expirada",
  CANCELLED: "Cancelada",
}

const PROMOTION_CLASS: Record<string, string> = {
  DRAFT:     NEUTRAL,
  ACTIVE:    EMERALD,
  PAUSED:    AMBER,
  EXPIRED:   NEUTRAL,
  CANCELLED: DESTRUCTIVE,
}

export function PromotionBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", PROMOTION_CLASS[status])}>
      {PROMOTION_LABEL[status] ?? status}
    </Badge>
  )
}

/* --------------------------------- Coupon --------------------------------- */

const COUPON_LABEL: Record<string, string> = {
  ACTIVE:    "Ativo",
  EXHAUSTED: "Esgotado",
  CANCELLED: "Cancelado",
}

const COUPON_CLASS: Record<string, string> = {
  ACTIVE:    EMERALD,
  EXHAUSTED: NEUTRAL,
  CANCELLED: DESTRUCTIVE,
}

export function CouponBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", COUPON_CLASS[status])}>
      {COUPON_LABEL[status] ?? status}
    </Badge>
  )
}

/* ====================== Fase 3 — FSMs do Financeiro profundo ====================== */

const SKY = "bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300"

/* -------------------------------- Expense -------------------------------- */
// ⚠️ chave de cancelamento é CANCELLED (inglês), não CANCELADA

const EXPENSE_CLASS: Record<string, string> = {
  PENDENTE:  AMBER,
  PAGA:      EMERALD,
  CANCELLED: NEUTRAL,
}

export function ExpenseBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", EXPENSE_CLASS[status])}>
      {EXPENSE_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* -------------------------------- Payable -------------------------------- */

const PAYABLE_CLASS: Record<string, string> = {
  OPEN:           AMBER,
  PARTIALLY_PAID: SKY,
  PAID:           EMERALD,
  CANCELLED:      NEUTRAL,
}

export function PayableBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", PAYABLE_CLASS[status])}>
      {PAYABLE_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ------------------------------ Installment ------------------------------ */

const INSTALLMENT_CLASS: Record<string, string> = {
  OPEN:      AMBER,
  PAID:      EMERALD,
  CANCELLED: NEUTRAL,
}

export function InstallmentBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", INSTALLMENT_CLASS[status])}>
      {INSTALLMENT_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ----------------------------- Reconciliation ----------------------------- */

const RECONCILIATION_CLASS: Record<string, string> = {
  OPEN:   AMBER,
  CLOSED: EMERALD,
}

export function ReconciliationBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", RECONCILIATION_CLASS[status])}>
      {RECONCILIATION_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ------------------------------- Statement ------------------------------- */

const STATEMENT_CLASS: Record<string, string> = {
  PENDING:   AMBER,
  MATCHED:   EMERALD,
  DISMISSED: NEUTRAL,
}

export function StatementBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", STATEMENT_CLASS[status])}>
      {STATEMENT_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* -------------------------------- Transfer -------------------------------- */

const TRANSFER_CLASS: Record<string, string> = {
  REQUESTED: AMBER,
  COMPLETED: EMERALD,
  FAILED:    DESTRUCTIVE,
}

export function TransferBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", TRANSFER_CLASS[status])}>
      {TRANSFER_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ===================== Fase 4 — Relacionamento e Administração ===================== */

/* ------------------------------- NpsSurvey ------------------------------- */

const NPS_SURVEY_CLASS: Record<string, string> = {
  PENDING:   AMBER,
  SENT:      SKY,
  RESPONDED: EMERALD,
  EXPIRED:   NEUTRAL,
}

export function NpsSurveyBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", NPS_SURVEY_CLASS[status])}>
      {NPS_SURVEY_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ---------------------------- CommunicationLog ---------------------------- */
// SENT(emerald) · SCHEDULED(sky) · FAILED(destructive) · todos SKIPPED_*(muted)

const COMM_LOG_CLASS: Record<string, string> = {
  SENT:                     EMERALD,
  SCHEDULED:                SKY,
  FAILED:                   DESTRUCTIVE,
  SKIPPED_QUIET_HOURS:      NEUTRAL,
  SKIPPED_NO_CONSENT:       NEUTRAL,
  SKIPPED_CHANNEL_DISABLED: NEUTRAL,
  SKIPPED_NO_TEMPLATE:      NEUTRAL,
}

export function CommunicationLogBadge({ status }: { status: string }) {
  return (
    <Badge variant="outline" className={cn("font-normal", COMM_LOG_CLASS[status] ?? NEUTRAL)}>
      {COMMUNICATION_LOG_STATUS_LABELS[status] ?? status}
    </Badge>
  )
}

/* ------------------------------- NPS score ------------------------------- */
// Faixa NPS (apenas display): 0–6 detrator · 7–8 neutro · 9–10 promotor

export function NpsScoreChip({ score }: { score: number | null | undefined }) {
  if (score == null) return <span className="text-muted-foreground">—</span>
  const cls =
    score <= 6 ? DESTRUCTIVE
    : score <= 8 ? AMBER
    : EMERALD
  return (
    <span className={cn("inline-flex h-6 min-w-6 items-center justify-center rounded-full border px-2 text-xs font-medium tabular-nums", cls)}>
      {score}
    </span>
  )
}
