"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { CheckCircle } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { PaymentBadge } from "@/components/FsmBadge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { formatBRL } from "@/lib/utils"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"

/**
 * Recebimentos do dia — superfície de balcão.
 *
 * Fonte: `GET /payments/today`, rota escopada por construção ao dia civil do
 * tenant (sem parâmetro de data, sem totais — docs/s-operador-backend.md §2).
 * Casa por `created_at` OU `paid_at`: a cobrança criada ontem e recebida hoje é
 * recebimento de hoje.
 *
 * A lista mostra transações; nenhuma soma. Somar o dia inteiro é resultado do
 * negócio, e é o dono quem o vê.
 */

interface Payment {
  payment_id: string
  customer_id: string | null
  appointment_id: string | null
  net_charged_amount: number
  payment_method: string
  payment_submethod: string | null
  provider: string
  status: string
  created_at: string
  paid_at?: string | null
}

interface Customer { id: string; name: string }
interface FeeWarning { fee_source: string; message: string }
interface ConfirmResponse { payment?: Payment; fee_warning: FeeWarning | null }

// Mesmo vocabulário do PaymentBadge (FsmBadge) — o filtro e a coluna Situação
// nomeiam o mesmo estado com a mesma palavra.
const STATUS_LABELS: Record<string, string> = {
  all: "Todas", PENDING: "Pendente", CONFIRMED: "Confirmado",
  FAILED: "Falhou", CANCELLED: "Cancelado", REFUNDED: "Estornado",
}

function methodLabel(p: Payment) {
  return p.payment_method === "MAQUININHA" && p.payment_submethod
    ? PAYMENT_METHOD_LABELS[`MAQUININHA_${p.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
    : PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method
}

function hourLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

export default function RecebimentosPage() {
  const [payments, setPayments] = useState<Payment[]>([])
  const [customerMap, setCustomerMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState("all")
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setPayments(await api.get<Payment[]>("/payments/today"))
      try {
        const cust = await api.get<Customer[]>("/customers/")
        setCustomerMap(new Map(cust.map((c) => [c.id, c.name])))
      } catch { /* nomes ficam como ID */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(
    () => payments.filter((p) => statusFilter === "all" || p.status === statusFilter),
    [payments, statusFilter],
  )

  const pendingCount = useMemo(
    () => payments.filter((p) => p.status === "PENDING").length,
    [payments],
  )

  async function handleConfirm(payment: Payment) {
    setBusy(payment.payment_id)
    try {
      const res = await api.post<ConfirmResponse>(
        `/payments/${payment.payment_id}/confirm-manual`,
        { payment_submethod: payment.payment_submethod },
      )
      toast.success("Recebimento confirmado")
      if (res?.fee_warning) toast.warning(res.fee_warning.message)
      load()
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao confirmar o recebimento")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Financeiro"
        title="Recebimentos do dia"
        description={
          pendingCount > 0
            ? `${payments.length} transação(ões) hoje · ${pendingCount} pendente(s)`
            : `${payments.length} transação(ões) hoje`
        }
      />

      <div className="flex items-end gap-4">
        <div className="space-y-1">
          <Label>Situação</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-44">
              <SelectValue>{STATUS_LABELS[statusFilter] ?? statusFilter}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {["all", "PENDING", "CONFIRMED", "FAILED", "CANCELLED", "REFUNDED"].map((s) => (
                <SelectItem key={s} value={s}>{STATUS_LABELS[s]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title={statusFilter === "all" ? "Nenhum recebimento hoje" : "Nenhum recebimento nesta situação"}
          description="Cada pagamento registrado na conclusão de um atendimento aparece aqui."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Hora</th>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Método</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Situação</th>
                <th className="px-4 py-3 text-left font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((p) => {
                const customerName = p.customer_id ? (customerMap.get(p.customer_id) ?? p.customer_id) : "—"
                const isPendingManual = p.status === "PENDING" && p.provider === "manual"
                return (
                  <tr key={p.payment_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 tabular-nums text-muted-foreground">
                      {hourLabel(p.paid_at ?? p.created_at)}
                    </td>
                    <td className="px-4 py-3">{customerName}</td>
                    <td className="px-4 py-3">{methodLabel(p)}</td>
                    <td className="px-4 py-3 text-right font-medium">{formatBRL(p.net_charged_amount)}</td>
                    <td className="px-4 py-3"><PaymentBadge status={p.status} /></td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <Link href={`/payments/${p.payment_id}`} className="text-xs text-primary hover:underline">
                          Ver detalhes
                        </Link>
                        {isPendingManual && (
                          <Dialog>
                            <DialogTrigger render={<Button size="sm" variant="outline" className="h-7 gap-1.5 px-2 text-xs" />}>
                              <CheckCircle className="h-3.5 w-3.5" /> Confirmar
                            </DialogTrigger>
                            <DialogContent>
                              <DialogHeader>
                                <DialogTitle>Confirmar recebimento</DialogTitle>
                                <DialogDescription>
                                  Confirma o recebimento de {formatBRL(p.net_charged_amount)} de {customerName}?
                                </DialogDescription>
                              </DialogHeader>
                              <DialogFooter>
                                <DialogClose render={<Button variant="outline" />}>Cancelar</DialogClose>
                                <DialogClose render={<Button />} onClick={() => handleConfirm(p)}
                                  disabled={busy === p.payment_id}>
                                  Confirmar
                                </DialogClose>
                              </DialogFooter>
                            </DialogContent>
                          </Dialog>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
