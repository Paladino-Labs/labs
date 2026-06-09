"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { Badge } from "@/components/ui/badge"
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

interface Movement {
  movement_id: string
  account_id: string
  type: string          // "INFLOW" | "OUTFLOW"
  amount: number
  source_type: string
  source_id: string
  occurred_at: string
  created_at: string
}

interface FinancialAccount {
  id: string
  name: string
}

const TYPE_LABELS: Record<string, string> = {
  all:     "Todos",
  INFLOW:  "Entrada",
  OUTFLOW: "Saída",
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  payment:           "Pagamento",
  commission_payout: "Pagamento de comissão",
  manual:            "Lançamento manual",
  refund:            "Reembolso",
  subscription:      "Assinatura",
  package:           "Pacote",
}

export default function MovimentacoesPage() {
  const [movements, setMovements] = useState<Movement[]>([])
  const [accountMap, setAccountMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [accountFilter, setAccountFilter] = useState("all")
  const [typeFilter, setTypeFilter] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [accounts, setAccounts] = useState<FinancialAccount[]>([])

  useEffect(() => {
    api.get<FinancialAccount[]>("/financial/accounts")
      .then((data) => {
        setAccounts(data)
        setAccountMap(new Map(data.map((a) => [a.id, a.name])))
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    setLoading(true)
    setError(null)

    const params = new URLSearchParams()
    if (accountFilter !== "all") params.set("account_id", accountFilter)
    if (typeFilter !== "all") params.set("type", typeFilter)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)

    const query = params.toString()
    api.get<Movement[]>(`/financial/movements${query ? `?${query}` : ""}`)
      .then(setMovements)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [accountFilter, typeFilter, dateFrom, dateTo])

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide">Movimentações</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Filtros</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4">
          <div className="space-y-1">
            <Label>Conta</Label>
            <Select value={accountFilter} onValueChange={(v) => v && setAccountFilter(v)}>
              <SelectTrigger className="w-44">
                <SelectValue>
                  {accountFilter === "all"
                    ? "Todas as contas"
                    : (accountMap.get(accountFilter) ?? "Caixa principal")}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas as contas</SelectItem>
                {accounts.map((a) => (
                  <SelectItem key={a.id} value={a.id}>{a.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label>Tipo</Label>
            <Select value={typeFilter} onValueChange={(v) => v && setTypeFilter(v)}>
              <SelectTrigger className="w-36">
                <SelectValue>
                  {TYPE_LABELS[typeFilter] ?? typeFilter}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="INFLOW">Entrada</SelectItem>
                <SelectItem value="OUTFLOW">Saída</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1">
            <Label htmlFor="mov-date-from">De</Label>
            <Input
              id="mov-date-from"
              type="date"
              value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)}
              className="w-40"
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="mov-date-to">Até</Label>
            <Input
              id="mov-date-to"
              type="date"
              value={dateTo}
              onChange={(e) => setDateTo(e.target.value)}
              className="w-40"
            />
          </div>
        </CardContent>
      </Card>

      {loading && (
        <p className="text-sm text-muted-foreground">Carregando movimentações...</p>
      )}

      {error && (
        <p className="text-sm text-destructive">Não foi possível carregar as movimentações.</p>
      )}

      {!loading && !error && movements.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nenhuma movimentação encontrada para os filtros selecionados.
        </p>
      )}

      {!loading && movements.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Conta</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-left font-medium">Descrição</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {movements.map((m) => {
                const isInflow = m.type === "INFLOW"
                const accountName = accountMap.get(m.account_id) ?? "Caixa principal"
                return (
                  <tr key={m.movement_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDateTime(m.occurred_at ?? m.created_at)}
                    </td>
                    <td className="px-4 py-3">{accountName}</td>
                    <td className="px-4 py-3">
                      <Badge variant={isInflow ? "default" : "destructive"}>
                        {isInflow ? "Entrada" : "Saída"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {SOURCE_TYPE_LABELS[m.source_type] ?? m.source_type}
                    </td>
                    <td className={`px-4 py-3 text-right font-medium ${isInflow ? "text-success" : "text-destructive"}`}>
                      {formatBRL(m.amount)}
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
