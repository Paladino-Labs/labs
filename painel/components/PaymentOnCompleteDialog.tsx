"use client"

import { useEffect, useState } from "react"
import { Banknote, CheckCircle, CreditCard, KeyRound, QrCode } from "lucide-react"
import { api } from "@/lib/api"
import { PAYMENT_METHOD_GROUPS, PAYMENT_METHOD_OPTIONS } from "@/lib/constants"
import { formatBRL } from "@/lib/utils"
import { FeeWarningBanner } from "@/components/FeeWarningBanner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

// ── Types ─────────────────────────────────────────────────────────────────────

const METHOD_ICONS: Record<string, React.ElementType> = {
  CASH:           Banknote,
  CHAVE_PIX:      KeyRound,
  MAQUININHA_PIX: QrCode,
}

interface FeeWarning {
  fee_source: string
  message: string
}

interface PaymentCreateResponse {
  payment_id: string
}

interface ConfirmResult {
  payment: {
    payment_id: string
    net_charged_amount: number
    provider_fee: number
    payment_method: string
    payment_submethod?: string | null
  }
  fee_warning: FeeWarning | null
}

interface AvailableCredit {
  has_credit:      boolean
  credit_id:       string | null
  service_name:    string | null
  remaining_cotas: number | null
}

export interface PaymentOnCompleteDialogProps {
  open: boolean
  appointment: {
    id: string
    total_amount: number
    customer_id?: string | null
    customer_name?: string | null
    services: Array<{ service_name: string; price?: number }>
  }
  onSuccess: () => void
  onClose: () => void
}

// ── Component ─────────────────────────────────────────────────────────────────

export function PaymentOnCompleteDialog({
  open,
  appointment,
  onSuccess,
  onClose,
}: PaymentOnCompleteDialogProps) {
  const [grossAmount, setGrossAmount] = useState("")
  const [method, setMethod] = useState<string | null>(null)
  const [phase, setPhase] = useState<"form" | "loading" | "result">("form")
  const [feeWarning, setFeeWarning] = useState<FeeWarning | null>(null)
  const [feeWarningDismissed, setFeeWarningDismissed] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [availableCredit, setAvailableCredit] = useState<AvailableCredit | null>(null)
  const [usingCredit, setUsingCredit] = useState(false)

  // Reset whenever the dialog opens with (possibly) a different appointment
  useEffect(() => {
    if (open) {
      setGrossAmount(appointment.total_amount > 0 ? String(appointment.total_amount) : "")
      setMethod(null)
      setPhase("form")
      setFeeWarning(null)
      setFeeWarningDismissed(false)
      setError(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, appointment.id])

  // Fetch any quota credit available for this appointment's service
  useEffect(() => {
    if (!open || !appointment.id) return
    setAvailableCredit(null)
    api.get<AvailableCredit>(`/appointments/${appointment.id}/available-credit`)
      .then(setAvailableCredit)
      .catch(() => setAvailableCredit({ has_credit: false, credit_id: null,
                                        service_name: null, remaining_cotas: null }))
  }, [open, appointment.id])

  const parsedAmount = parseFloat(grossAmount)
  const amountValid  = !isNaN(parsedAmount) && parsedAmount > 0

  const serviceNames = appointment.services.map((s) => s.service_name).join(", ")

  // ── Confirm with payment ───────────────────────────────────────────────────

  async function handleConfirm() {
    if (!amountValid) { setError("Informe um valor válido."); return }
    if (!method)      { setError("Selecione o método de pagamento."); return }

    const cfg = PAYMENT_METHOD_OPTIONS.find((m) => m.key === method)!

    setError(null)
    setPhase("loading")

    try {
      const created = await api.post<PaymentCreateResponse>("/payments", {
        customer_id:       appointment.customer_id ?? null,
        appointment_id:    appointment.id,
        gross_amount:      parsedAmount,
        payment_method:    cfg.payment_method,
        payment_submethod: cfg.payment_submethod,
        provider:          "manual",
      })

      const confirmed = await api.post<ConfirmResult>(
        `/payments/${created.payment_id}/confirm-manual`,
        { payment_submethod: cfg.payment_submethod }
      )

      await api.patch(`/appointments/${appointment.id}/complete`, {})

      if (confirmed.fee_warning) {
        setFeeWarning(confirmed.fee_warning)
        setFeeWarningDismissed(false)
        setPhase("result")
      } else {
        onSuccess()
      }
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao registrar pagamento.")
      setPhase("form")
    }
  }

  // ── Consume quota credit ───────────────────────────────────────────────────

  async function handleUseCredit() {
    setUsingCredit(true)
    setError(null)
    setPhase("loading")
    try {
      await api.patch(`/appointments/${appointment.id}/complete`, { use_credit: true })
      onSuccess()
    } catch (err: unknown) {
      const msg = (err as Error).message ?? ""
      setError(
        msg.includes("409") || msg.toLowerCase().includes("cota")
          ? "Cota não disponível para este serviço."
          : "Erro ao consumir cota."
      )
      setPhase("form")
    } finally {
      setUsingCredit(false)
    }
  }

  // ── Complete without payment ───────────────────────────────────────────────

  async function handleCompleteOnly() {
    setError(null)
    setPhase("loading")
    try {
      await api.patch(`/appointments/${appointment.id}/complete`, { use_credit: false })
      onSuccess()
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao concluir agendamento.")
      setPhase("form")
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Registrar pagamento</DialogTitle>
        </DialogHeader>

        {/* ── Loading ──────────────────────────────────────────────────────── */}
        {phase === "loading" && (
          <div className="py-10 text-center text-sm text-muted-foreground">
            Processando…
          </div>
        )}

        {/* ── Result (fee warning) ─────────────────────────────────────────── */}
        {phase === "result" && (
          <div className="space-y-4 py-2">
            <div className="flex items-center gap-2 text-sm font-medium text-green-700">
              <CheckCircle className="h-5 w-5" />
              Pagamento confirmado
            </div>

            {feeWarning && !feeWarningDismissed && (
              <FeeWarningBanner
                feeSource={feeWarning.fee_source}
                message={feeWarning.message}
                onDismiss={() => setFeeWarningDismissed(true)}
                onConfigureClick={() => {
                  setFeeWarningDismissed(true)
                  window.open("/financeiro/taxas", "_blank")
                }}
              />
            )}

            <DialogFooter>
              <Button className="w-full" onClick={onSuccess}>
                Fechar
              </Button>
            </DialogFooter>
          </div>
        )}

        {/* ── Form ─────────────────────────────────────────────────────────── */}
        {phase === "form" && (
          <>
            {(appointment.customer_name || serviceNames) && (
              <div className="space-y-0.5 text-sm text-muted-foreground -mt-1">
                {appointment.customer_name && <p>{appointment.customer_name}</p>}
                {serviceNames && <p>{serviceNames}</p>}
              </div>
            )}

            {availableCredit?.has_credit && (
              <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 space-y-2">
                <p className="text-sm font-medium text-primary">
                  Cota disponível — {availableCredit.service_name ?? "Serviço"}
                </p>
                <p className="text-xs text-muted-foreground">
                  {availableCredit.remaining_cotas} cota{availableCredit.remaining_cotas !== 1 ? "s" : ""} restante{availableCredit.remaining_cotas !== 1 ? "s" : ""}
                </p>
                <Button
                  size="sm"
                  className="w-full"
                  onClick={handleUseCredit}
                  disabled={usingCredit}
                >
                  {usingCredit ? "Consumindo…" : "Usar cota (sem cobrança)"}
                </Button>
              </div>
            )}

            <div className="space-y-5">
              {/* Valor */}
              <div className="space-y-1.5">
                <Label htmlFor="pod-amount">Valor</Label>
                <Input
                  id="pod-amount"
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="0,00"
                  value={grossAmount}
                  onChange={(e) => setGrossAmount(e.target.value)}
                />
                {amountValid && (
                  <p className="text-xs text-muted-foreground">{formatBRL(parsedAmount)}</p>
                )}
              </div>

              {/* Método */}
              <div className="space-y-3">
                <Label>Método de pagamento</Label>
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
            </div>

            <DialogFooter className="flex-col gap-2 sm:flex-col">
              <Button
                className="w-full"
                disabled={!amountValid || !method}
                onClick={handleConfirm}
              >
                Confirmar pagamento e concluir
              </Button>
              <Button
                variant="ghost"
                className="w-full"
                onClick={handleCompleteOnly}
              >
                Concluir sem registrar pagamento
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}
