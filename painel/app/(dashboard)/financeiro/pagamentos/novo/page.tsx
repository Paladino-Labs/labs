"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import Link from "next/link"
import { Banknote, CheckCircle, CreditCard, KeyRound, QrCode } from "lucide-react"
import { api } from "@/lib/api"
import { PAYMENT_METHOD_GROUPS, PAYMENT_METHOD_LABELS, PAYMENT_METHOD_OPTIONS } from "@/lib/constants"
import { useAuth } from "@/context/AuthContext"
import { formatBRL } from "@/lib/utils"
import { CustomerAutocomplete } from "@/components/CustomerAutocomplete"
import { FeeWarningBanner } from "@/components/FeeWarningBanner"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

// ── Types ─────────────────────────────────────────────────────────────────────

interface AppointmentOption {
  id: string
  start_at: string
  status: string
  services?: Array<{ service_name: string }>
}

interface PaymentCreateResponse {
  payment_id: string
}

interface FeeWarning {
  fee_source: string
  message: string
}

// ConfirmManualResponse do backend é flat — todos os campos de Payment
// + fee_warning no mesmo objeto (não existe chave "payment" aninhada).
interface ConfirmResult {
  payment_id: string
  net_charged_amount: number
  provider_fee: number
  payment_method: string
  payment_submethod?: string | null
  fee_warning: FeeWarning | null
}

// ── Payment method config ─────────────────────────────────────────────────────

const METHOD_ICONS: Record<string, React.ElementType> = {
  CASH:           Banknote,
  CHAVE_PIX:      KeyRound,
  MAQUININHA_PIX: QrCode,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatApptLabel(a: AppointmentOption): string {
  const date = new Date(a.start_at).toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  })
  const services = a.services?.map((s) => s.service_name).join(", ") ?? ""
  return services ? `${date} — ${services}` : date
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function NovoPageWrapper() {
  const { role } = useAuth()

  if (role && role !== "OWNER" && role !== "ADMIN") {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
        <p className="text-lg font-medium">Acesso restrito</p>
        <p className="text-sm text-muted-foreground">
          Esta área é exclusiva para Proprietários e Administradores.
        </p>
        <Link href="/financeiro/pagamentos" className="text-sm text-primary hover:underline">
          ← Voltar para Pagamentos
        </Link>
      </div>
    )
  }

  return <NovoPageContent />
}

function NovoPageContent() {
  const router = useRouter()

  // ── Form state ────────────────────────────────────────────────────────────
  const [customerId, setCustomerId] = useState<string | null>(null)
  const [appointments, setAppointments] = useState<AppointmentOption[]>([])
  const [loadingAppts, setLoadingAppts] = useState(false)
  const [appointmentId, setAppointmentId] = useState<string | null>(null)
  const [grossAmount, setGrossAmount] = useState("")
  const [method, setMethod] = useState<string | null>(null)

  // ── UI state ──────────────────────────────────────────────────────────────
  const [phase, setPhase] = useState<"form" | "loading" | "success">("form")
  const [confirmResult, setConfirmResult] = useState<ConfirmResult | null>(null)
  const [feeWarningDismissed, setFeeWarningDismissed] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── Load appointments when customer is selected ───────────────────────────
  useEffect(() => {
    if (!customerId) {
      setAppointments([])
      setAppointmentId(null)
      return
    }
    setLoadingAppts(true)
    api
      .get<AppointmentOption[]>(`/appointments?customer_id=${customerId}`)
      .then(setAppointments)
      .catch(() => setAppointments([]))
      .finally(() => setLoadingAppts(false))
  }, [customerId])

  function handleCustomerChange(id: string, _name: string) {
    setCustomerId(id || null)
    setAppointmentId(null)
    setError(null)
  }

  // ── Submit ────────────────────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!customerId) { setError("Selecione um cliente."); return }
    if (!grossAmount || isNaN(parseFloat(grossAmount)) || parseFloat(grossAmount) <= 0) {
      setError("Informe um valor válido.")
      return
    }
    if (!method) { setError("Selecione o método de pagamento."); return }

    const cfg = PAYMENT_METHOD_OPTIONS.find((m) => m.key === method)!

    setError(null)
    setPhase("loading")

    try {
      const created = await api.post<PaymentCreateResponse>("/payments", {
        customer_id:       customerId,
        appointment_id:    appointmentId ?? null,
        gross_amount:      parseFloat(grossAmount),
        payment_method:    cfg.payment_method,
        payment_submethod: cfg.payment_submethod,
      })

      const confirmed = await api.post<ConfirmResult>(
        `/payments/${created.payment_id}/confirm-manual`,
        { payment_submethod: cfg.payment_submethod }
      )

      setConfirmResult(confirmed)
      setFeeWarningDismissed(false)
      setPhase("success")
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Erro ao registrar pagamento.")
      setPhase("form")
    }
  }

  function handleReset() {
    setCustomerId(null)
    setAppointments([])
    setAppointmentId(null)
    setGrossAmount("")
    setMethod(null)
    setConfirmResult(null)
    setFeeWarningDismissed(false)
    setError(null)
    setPhase("form")
  }

  const parsedAmount = parseFloat(grossAmount)
  const amountValid = !isNaN(parsedAmount) && parsedAmount > 0

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-lg mx-auto space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/financeiro/pagamentos"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ← Voltar
        </Link>
      </div>

      <h1 className="font-display text-3xl tracking-wide">Registrar Pagamento</h1>

      {/* ── Loading ─────────────────────────────────────────────────────── */}
      {phase === "loading" && (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">Registrando pagamento...</p>
          </CardContent>
        </Card>
      )}

      {/* ── Success ─────────────────────────────────────────────────────── */}
      {phase === "success" && confirmResult && (
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base font-medium text-green-700">
                <CheckCircle className="h-5 w-5" />
                Pagamento confirmado
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Valor líquido</span>
                <span className="font-semibold text-base">
                  {formatBRL(confirmResult.net_charged_amount)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Taxa aplicada</span>
                <span>{formatBRL(confirmResult.provider_fee)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Método</span>
                <span>
                  {confirmResult.payment_method === "MAQUININHA" && confirmResult.payment_submethod
                    ? PAYMENT_METHOD_LABELS[`MAQUININHA_${confirmResult.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
                    : PAYMENT_METHOD_LABELS[confirmResult.payment_method] ?? confirmResult.payment_method}
                </span>
              </div>
            </CardContent>
          </Card>

          {confirmResult.fee_warning && !feeWarningDismissed && (
            <FeeWarningBanner
              feeSource={confirmResult.fee_warning.fee_source}
              message={confirmResult.fee_warning.message}
              onDismiss={() => setFeeWarningDismissed(true)}
              onConfigureClick={() => router.push("/financeiro/taxas")}
            />
          )}

          <div className="flex gap-3">
            <Button variant="outline" className="flex-1" onClick={handleReset}>
              Novo pagamento
            </Button>
            <Button className="flex-1" onClick={() => router.push("/financeiro/pagamentos")}>
              Ver lista
            </Button>
          </div>
        </div>
      )}

      {/* ── Form ────────────────────────────────────────────────────────── */}
      {phase === "form" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium">Dados do pagamento</CardTitle>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-5">

              {/* ── Cliente ─────────────────────────────────────────────── */}
              <div className="space-y-1.5">
                <Label>Cliente *</Label>
                <CustomerAutocomplete
                  value={customerId}
                  onChange={handleCustomerChange}
                  placeholder="Buscar cliente por nome ou telefone…"
                />
              </div>

              {/* ── Agendamento ─────────────────────────────────────────── */}
              {customerId && (
                <div className="space-y-1.5">
                  <Label>Agendamento (opcional)</Label>
                  {loadingAppts ? (
                    <p className="text-sm text-muted-foreground">Buscando agendamentos...</p>
                  ) : appointments.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Nenhum agendamento encontrado para este cliente.
                    </p>
                  ) : (
                    <Select
                      value={appointmentId ?? "none"}
                      onValueChange={(v) => setAppointmentId(v === "none" ? null : v)}
                    >
                      <SelectTrigger>
                        <SelectValue>
                          {appointmentId && appointmentId !== "none"
                            ? formatApptLabel(appointments.find((a) => a.id === appointmentId) ?? appointments[0])
                            : "Sem agendamento"}
                        </SelectValue>
                      </SelectTrigger>
                      <SelectContent className="w-[var(--radix-select-trigger-width)]">
                        <SelectItem value="none">Sem agendamento</SelectItem>
                        {appointments.map((a) => (
                          <SelectItem key={a.id} value={a.id} className="whitespace-normal">
                            {formatApptLabel(a)}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )}

              {/* ── Valor ───────────────────────────────────────────────── */}
              <div className="space-y-1.5">
                <Label htmlFor="gross-amount">Valor *</Label>
                <Input
                  id="gross-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="0,00"
                  value={grossAmount}
                  onChange={(e) => setGrossAmount(e.target.value)}
                />
                {amountValid && (
                  <p className="text-xs text-muted-foreground">
                    {formatBRL(parsedAmount)}
                  </p>
                )}
              </div>

              {/* ── Método de pagamento ──────────────────────────────────── */}
              <div className="space-y-3">
                <Label>Método de pagamento *</Label>
                {PAYMENT_METHOD_GROUPS.map((group) => (
                  <div key={group} className="space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">{group}</p>
                    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                      {PAYMENT_METHOD_OPTIONS.filter((o) => o.group === group).map(
                        ({ key, label, shortLabel }) => {
                          const Icon = METHOD_ICONS[key] ?? CreditCard
                          const selected = method === key
                          return (
                            <button
                              key={key}
                              type="button"
                              title={label}
                              onClick={() => setMethod(key)}
                              className={
                                selected
                                  ? "flex items-center gap-2 rounded-lg border-2 border-primary bg-primary/5 px-3 py-2 text-xs font-medium text-primary transition-all"
                                  : "flex items-center gap-2 rounded-lg border border-border px-3 py-2 text-xs text-foreground transition-all hover:border-primary/50 hover:bg-muted/40"
                              }
                            >
                              <Icon className="h-4 w-4 shrink-0" />
                              {shortLabel}
                            </button>
                          )
                        }
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button
                type="submit"
                className="w-full"
                disabled={!customerId || !amountValid || !method}
              >
                Confirmar pagamento
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
