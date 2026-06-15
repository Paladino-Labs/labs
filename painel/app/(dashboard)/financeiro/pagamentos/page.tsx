"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { CheckCircle } from "lucide-react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
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
import { formatBRL, formatDateTime } from "@/lib/utils"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"

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
}

interface Customer { id: string; name: string }
interface FeeWarning { fee_source: string; message: string }
interface ConfirmResponse { payment?: Payment; fee_warning: FeeWarning | null }

const STATUS_LABELS: Record<string, string> = {
  all: "Todos", PENDING: "Pendente", CONFIRMED: "Confirmado",
  FAILED: "Falhou", CANCELLED: "Cancelado", REFUNDED: "Estornado",
}
const PAGE_SIZE = 20

function methodLabel(p: Payment) {
  return p.payment_method === "MAQUININHA" && p.payment_submethod
    ? PAYMENT_METHOD_LABELS[`MAQUININHA_${p.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
    : PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method
}

export default function PagamentosPage() {
  const { role } = useAuth()
  const canConfirm = role === "OWNER" || role === "ADMIN"

  const [payments, setPayments] = useState<Payment[]>([])
  const [customerMap, setCustomerMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [statusFilter, setStatusFilter] = useState("all")
  const [methodFilter, setMethodFilter] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [page, setPage] = useState(1)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.get<Payment[]>("/payments")
      setPayments(data)
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

  const uniqueMethods = useMemo(
    () => Array.from(new Set(payments.map((p) => p.payment_method))).filter(Boolean),
    [payments],
  )

  const filtered = useMemo(() => payments.filter((p) => {
    if (statusFilter !== "all" && p.status !== statusFilter) return false
    if (methodFilter !== "all" && p.payment_method !== methodFilter) return false
    if (dateFrom && p.created_at < dateFrom) return false
    if (dateTo && p.created_at > dateTo + "T23:59:59") return false
    return true
  }), [payments, statusFilter, methodFilter, dateFrom, dateTo])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  // Mantém a página dentro do intervalo válido quando os filtros mudam.
  const safePage = Math.min(page, totalPages)
  const pageItems = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  async function handleConfirm(payment: Payment) {
    try {
      const res = await api.post<ConfirmResponse>(
        `/payments/${payment.payment_id}/confirm-manual`,
        { payment_submethod: payment.payment_submethod },
      )
      toast.success("Pagamento confirmado")
      if (res?.fee_warning) toast.warning(`${res.fee_warning.fee_source}: ${res.fee_warning.message}`)
      load()
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao confirmar pagamento")
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Pagamentos" description={`${filtered.length} registro(s)`}>
        <Button render={<Link href="/financeiro/pagamentos/novo" />}>+ Registrar pagamento</Button>
      </PageHeader>

      <Card>
        <CardHeader><CardTitle className="text-base font-medium">Filtros</CardTitle></CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <div className="space-y-1">
            <Label>Status</Label>
            <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
              <SelectTrigger className="w-40"><SelectValue>{STATUS_LABELS[statusFilter] ?? statusFilter}</SelectValue></SelectTrigger>
              <SelectContent>
                {["all", "PENDING", "CONFIRMED", "FAILED", "CANCELLED", "REFUNDED"].map((s) => (
                  <SelectItem key={s} value={s}>{STATUS_LABELS[s]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Método</Label>
            <Select value={methodFilter} onValueChange={(v) => v && setMethodFilter(v)}>
              <SelectTrigger className="w-40">
                <SelectValue>{methodFilter === "all" ? "Todos" : PAYMENT_METHOD_LABELS[methodFilter] ?? methodFilter}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {uniqueMethods.map((m) => (
                  <SelectItem key={m} value={m}>{PAYMENT_METHOD_LABELS[m] ?? m}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="date-from">De</Label>
            <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="date-to">Até</Label>
            <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState title="Nenhum pagamento" description="Nenhum pagamento para os filtros selecionados." />
      ) : (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Data</th>
                  <th className="px-4 py-3 text-left font-medium">Cliente</th>
                  <th className="px-4 py-3 text-left font-medium">Método</th>
                  <th className="px-4 py-3 text-right font-medium">Valor líquido</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                  <th className="px-4 py-3 text-left font-medium">Ações</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {pageItems.map((p) => {
                  const customerName = p.customer_id ? (customerMap.get(p.customer_id) ?? p.customer_id) : "—"
                  const isPendingManual = p.status === "PENDING" && p.provider === "manual"
                  return (
                    <tr key={p.payment_id} className="transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 text-muted-foreground">{formatDateTime(p.created_at)}</td>
                      <td className="px-4 py-3">{customerName}</td>
                      <td className="px-4 py-3">{methodLabel(p)}</td>
                      <td className="px-4 py-3 text-right font-medium">{formatBRL(p.net_charged_amount)}</td>
                      <td className="px-4 py-3"><PaymentBadge status={p.status} /></td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <Link href={`/payments/${p.payment_id}`} className="text-xs text-primary hover:underline">Ver detalhes</Link>
                          {canConfirm && isPendingManual && (
                            <Dialog>
                              <DialogTrigger render={<Button size="sm" variant="outline" className="h-7 gap-1.5 px-2 text-xs" />}>
                                <CheckCircle className="h-3.5 w-3.5" /> Confirmar
                              </DialogTrigger>
                              <DialogContent>
                                <DialogHeader>
                                  <DialogTitle>Confirmar pagamento</DialogTitle>
                                  <DialogDescription>Confirma o recebimento de {formatBRL(p.net_charged_amount)}?</DialogDescription>
                                </DialogHeader>
                                <DialogFooter>
                                  <DialogClose render={<Button variant="outline" />}>Cancelar</DialogClose>
                                  <DialogClose render={<Button />} onClick={() => handleConfirm(p)}>Confirmar</DialogClose>
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

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Página {safePage} de {totalPages}</span>
              <div className="flex gap-2">
                <Button size="sm" variant="outline" disabled={safePage <= 1} onClick={() => setPage(safePage - 1)}>Anterior</Button>
                <Button size="sm" variant="outline" disabled={safePage >= totalPages} onClick={() => setPage(safePage + 1)}>Próxima</Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
