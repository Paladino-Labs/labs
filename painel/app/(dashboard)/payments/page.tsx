"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import Link from "next/link"
import { formatBRL, formatDateTime } from "@/lib/utils"

interface Payment {
  payment_id: string
  customer_id: string | null
  appointment_id: string | null
  gross_catalog_amount: number
  net_charged_amount: number
  provider_fee: number
  payment_method: string
  provider: string
  status: string
  created_at: string
  paid_at: string | null
  refunded_at: string | null
}

const STATUS_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  PENDING:   { label: "Pendente",    variant: "secondary" },
  CONFIRMED: { label: "Confirmado",  variant: "default" },
  FAILED:    { label: "Falhou",      variant: "destructive" },
  CANCELLED: { label: "Cancelado",   variant: "outline" },
  REFUNDED:  { label: "Reembolsado", variant: "outline" },
}

export default function PaymentsPage() {
  const [payments, setPayments] = useState<Payment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  useEffect(() => {
    api<Payment[]>("/payments")
      .then(setPayments)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = payments.filter((p) => {
    if (dateFrom && p.created_at < dateFrom) return false
    if (dateTo && p.created_at > dateTo + "T23:59:59") return false
    return true
  })

  return (
    <div className="space-y-6">
      <h1 className="text-3xl tracking-wide">Pagamentos</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Filtrar por período</CardTitle>
        </CardHeader>
        <CardContent className="flex gap-4">
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
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Método</th>
                <th className="px-4 py-3 text-left font-medium">Provider</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((p) => {
                const badge = STATUS_BADGE[p.status] ?? { label: p.status, variant: "outline" as const }
                return (
                  <tr key={p.payment_id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDateTime(p.created_at)}
                    </td>
                    <td className="px-4 py-3">{p.payment_method}</td>
                    <td className="px-4 py-3 text-muted-foreground capitalize">{p.provider}</td>
                    <td className="px-4 py-3 text-right font-medium">
                      {formatBRL(p.net_charged_amount)}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={badge.variant}>{badge.label}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        href={`/payments/${p.payment_id}`}
                        className="text-xs text-primary hover:underline"
                      >
                        Ver detalhes
                      </Link>
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
