"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
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
import { EmptyState } from "@/components/empty-state"

interface Commission {
  commission_id: string
  professional_id: string
  policy_id: string | null
  appointment_id: string | null
  operation_type: string
  gross_amount: string | number
  commission_amount: string | number
  status: string
  due_date: string | null
  paid_at: string | null
  payout_id: string | null
  created_at: string
}

interface Professional {
  id: string
  name: string
}

const OPERATION_TYPE_LABELS: Record<string, string> = {
  APPOINTMENT: "Agendamento",
  PACKAGE: "Pacote",
}

type StatusFilter = "all" | "pending" | "PAID" | "REVERSED"

function isPending(status: string): boolean {
  return status === "CALCULATED" || status === "DUE"
}

function StatusBadge({ status }: { status: string }) {
  if (status === "CALCULATED") {
    return (
      <Badge className="border border-yellow-200 bg-yellow-100 text-yellow-800 hover:bg-yellow-100">
        Pendente
      </Badge>
    )
  }
  if (status === "DUE") {
    return (
      <Badge className="border border-amber-200 bg-amber-100 text-amber-800 hover:bg-amber-100">
        Vence em breve
      </Badge>
    )
  }
  if (status === "PAID") {
    return (
      <Badge className="border border-green-200 bg-green-100 text-green-800 hover:bg-green-100">
        Paga
      </Badge>
    )
  }
  if (status === "REVERSED") {
    return (
      <Badge className="border border-red-200 bg-red-100 text-red-800 hover:bg-red-100">
        Estornada
      </Badge>
    )
  }
  return <Badge variant="outline">{status}</Badge>
}

export default function HistoricoComissoesPage() {
  const [commissions, setCommissions] = useState<Commission[]>([])
  const [professionalMap, setProfessionalMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [professionalFilter, setProfessionalFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [professionals, setProfessionals] = useState<Professional[]>([])

  useEffect(() => {
    api.get<Professional[]>("/professionals")
      .then((data) => {
        setProfessionals(data)
        setProfessionalMap(new Map(data.map((p) => [p.id, p.name])))
      })
      .catch(() => {})

    fetchCommissions()
  }, [])

  function buildQueryParams() {
    const params = new URLSearchParams()
    if (professionalFilter !== "all") params.set("professional_id", professionalFilter)
    if (statusFilter === "PAID") params.set("status", "PAID")
    if (statusFilter === "REVERSED") params.set("status", "REVERSED")
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    return params.toString()
  }

  function fetchCommissions() {
    setLoading(true)
    setError(null)
    const qs = buildQueryParams()
    api.get<Commission[]>(`/commissions${qs ? `?${qs}` : ""}`)
      .then(setCommissions)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }

  function handleFilter() {
    fetchCommissions()
  }

  const displayed =
    statusFilter === "pending"
      ? commissions.filter((c) => isPending(c.status))
      : commissions

  const totalPending = displayed.reduce((sum, c) => {
    if (isPending(c.status)) return sum + Number(c.commission_amount)
    return sum
  }, 0)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-wide">Histórico de Comissões</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <Label>Profissional</Label>
            <Select value={professionalFilter} onValueChange={(v) => v && setProfessionalFilter(v)}>
              <SelectTrigger className="w-44">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                {professionals.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Status</Label>
            <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v as StatusFilter)}>
              <SelectTrigger className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="pending">Pendentes</SelectItem>
                <SelectItem value="PAID">Pagas</SelectItem>
                <SelectItem value="REVERSED">Estornadas</SelectItem>
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

          <Button onClick={handleFilter}>Filtrar</Button>
        </CardContent>
      </Card>

      {loading && (
        <p className="text-sm text-muted-foreground">Carregando comissões...</p>
      )}

      {error && (
        <p className="text-sm text-destructive">Não foi possível carregar as comissões.</p>
      )}

      {!loading && !error && displayed.length === 0 && (
        <EmptyState message="Nenhuma comissão encontrada para os filtros selecionados." />
      )}

      {!loading && !error && displayed.length > 0 && (
        <>
          <div className="overflow-hidden rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Data</th>
                  <th className="px-4 py-3 text-left font-medium">Profissional</th>
                  <th className="px-4 py-3 text-left font-medium">Tipo</th>
                  <th className="px-4 py-3 text-right font-medium">Valor bruto</th>
                  <th className="px-4 py-3 text-right font-medium">Comissão</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {displayed.map((c) => {
                  const profName = professionalMap.get(c.professional_id)
                    ?? c.professional_id.slice(0, 8) + "…"
                  const typeLabel = OPERATION_TYPE_LABELS[c.operation_type] ?? c.operation_type
                  return (
                    <tr key={c.commission_id} className="transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 text-muted-foreground">
                        {c.created_at
                          ? new Date(c.created_at).toLocaleString("pt-BR", {
                              dateStyle: "short",
                              timeStyle: "short",
                              timeZone: "America/Sao_Paulo",
                            })
                          : "—"}
                      </td>
                      <td className="px-4 py-3">{profName}</td>
                      <td className="px-4 py-3">{typeLabel}</td>
                      <td className="px-4 py-3 text-right">
                        {formatBRL(Number(c.gross_amount))}
                      </td>
                      <td className="px-4 py-3 text-right font-medium">
                        {formatBRL(Number(c.commission_amount))}
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={c.status} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>

          <div className="border-t border-border pt-4">
            <p className="text-sm font-bold">
              Total pendente: {formatBRL(totalPending)}
            </p>
          </div>
        </>
      )}
    </div>
  )
}
