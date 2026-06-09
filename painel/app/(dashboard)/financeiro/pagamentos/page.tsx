"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { CheckCircle, X } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatBRL, formatDateTime } from "@/lib/utils"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"

interface Payment {
  payment_id: string
  customer_id: string | null
  appointment_id: string | null
  gross_catalog_amount: number
  net_charged_amount: number
  provider_fee: number
  payment_method: string
  payment_submethod: string | null
  provider: string
  status: string
  created_at: string
  paid_at: string | null
  refunded_at: string | null
}

interface Customer {
  id: string
  name: string
}

interface FeeWarning {
  fee_source: string
  message: string
}

interface ConfirmManualResponse {
  payment: Payment
  fee_warning: FeeWarning | null
}

const STATUS_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  PENDING:   { label: "Pendente",    variant: "secondary" },
  CONFIRMED: { label: "Confirmado",  variant: "default" },
  FAILED:    { label: "Falhou",      variant: "destructive" },
  CANCELLED: { label: "Cancelado",   variant: "outline" },
  REFUNDED:  { label: "Reembolsado", variant: "outline" },
}

const STATUS_LABELS: Record<string, string> = {
  all:       "Todos",
  PENDING:   "Pendente",
  CONFIRMED: "Confirmado",
  FAILED:    "Falhou",
  CANCELLED: "Cancelado",
  REFUNDED:  "Reembolsado",
}

const METHOD_LABELS: Record<string, string> = {
  all:        "Todos",
  MAQUININHA: "Crédito/Débito",
  PIX:        "PIX",
  CASH:       "Dinheiro",
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

  const [confirming, setConfirming] = useState<string | null>(null)
  const [feeWarning, setFeeWarning] = useState<FeeWarning | null>(null)

  function loadData() {
    setLoading(true)
    setError(null)
    // Carrega payments e customers de forma independente:
    // falha em /customers não impede exibição dos pagamentos.
    api.get<Payment[]>("/payments")
      .then(setPayments)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))

    api.get<Customer[]>("/customers")
      .then((data) => setCustomerMap(new Map(data.map((c) => [c.id, c.name])))
      )
      .catch(() => {}) // falha silenciosa — nomes de clientes ficam como IDs
  }

  useEffect(() => {
    loadData()
  }, [])

  const uniqueMethods = Array.from(new Set(payments.map((p) => p.payment_method))).filter(Boolean)

  const filtered = payments.filter((p) => {
    if (statusFilter !== "all" && p.status !== statusFilter) return false
    if (methodFilter !== "all" && p.payment_method !== methodFilter) return false
    if (dateFrom && p.created_at < dateFrom) return false
    if (dateTo && p.created_at > dateTo + "T23:59:59") return false
    return true
  })

  async function handleConfirm(paymentId: string) {
    setConfirming(paymentId)
    try {
      const res = await api.post<ConfirmManualResponse>(`/payments/${paymentId}/confirm-manual`, {})
      if (res.fee_warning) {
        setFeeWarning(res.fee_warning)
      }
      loadData()
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Erro ao confirmar pagamento")
    } finally {
      setConfirming(null)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-3xl tracking-wide">Pagamentos</h1>
        <Link
          href="/financeiro/pagamentos/novo"
          className="text-sm font-medium text-primary hover:underline"
        >
          + Registrar pagamento
        </Link>
      </div>

      {feeWarning && (
        <div className="flex items-start gap-3 rounded-lg border border-warning bg-warning/10 px-4 py-3 text-sm text-warning-foreground">
          <span className="flex-1">
            <span className="font-medium">{feeWarning.fee_source}:</span> {feeWarning.message}
          </span>
          <button
            onClick={() => setFeeWarning(null)}
            className="shrink-0 text-muted-foreground hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <div className="space-y-1">
            <Label>Status</Label>
            <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
              <SelectTrigger className="w-40">
                <SelectValue>
                  {STATUS_LABELS[statusFilter] ?? statusFilter}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="PENDING">Pendente</SelectItem>
                <SelectItem value="CONFIRMED">Confirmado</SelectItem>
                <SelectItem value="FAILED">Falhou</SelectItem>
                <SelectItem value="CANCELLED">Cancelado</SelectItem>
                <SelectItem value="REFUNDED">Reembolsado</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Método</Label>
            <Select value={methodFilter} onValueChange={(v) => v && setMethodFilter(v)}>
              <SelectTrigger className="w-40">
                <SelectValue>
                  {METHOD_LABELS[methodFilter] ?? PAYMENT_METHOD_LABELS[methodFilter] ?? methodFilter}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {uniqueMethods.map((m) => (
                  <SelectItem key={m} value={m}>
                    {METHOD_LABELS[m] ?? PAYMENT_METHOD_LABELS[m] ?? m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="date-from">De</Label>
            <Input
              id="date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-40"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="date-to">Até</Label>
            <Input
              id="date-to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-40"
            />
          </div>
        </CardContent>
      </Card>

      {loading && (
        <p className="text-sm text-muted-foreground">Carregando pagamentos...</p>
      )}

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {!loading && !error && filtered.length === 0 && (
        <p className="text-sm text-muted-foreground">Nenhum pagamento encontrado.</p>
      )}

      {!loading && filtered.length > 0 && (
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
              {filtered.map((p) => {
                const badge = STATUS_BADGE[p.status] ?? { label: p.status, variant: "outline" as const }
                const customerName = p.customer_id ? (customerMap.get(p.customer_id) ?? p.customer_id) : "—"
                const isPendingManual = p.status === "PENDING" && p.provider === "manual"
                return (
                  <tr key={p.payment_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDateTime(p.created_at)}
                    </td>
                    <td className="px-4 py-3">{customerName}</td>
                    <td className="px-4 py-3">
                      {p.payment_method === "MAQUININHA" && p.payment_submethod
                        ? PAYMENT_METHOD_LABELS[`MAQUININHA_${p.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
                        : PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method}
                    </td>
                    <td className="px-4 py-3 text-right font-medium">
                      {formatBRL(p.net_charged_amount)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={badge.variant}>{badge.label}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-3">
                        <Link
                          href={`/payments/${p.payment_id}`}
                          className="text-xs text-primary hover:underline"
                        >
                          Ver detalhes
                        </Link>
                        {canConfirm && isPendingManual && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={confirming === p.payment_id}
                            onClick={() => handleConfirm(p.payment_id)}
                            className="h-7 gap-1.5 px-2 text-xs"
                          >
                            <CheckCircle className="h-3.5 w-3.5" />
                            {confirming === p.payment_id ? "..." : "Confirmar"}
                          </Button>
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
