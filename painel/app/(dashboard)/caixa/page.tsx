"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { ArrowDownCircle, ArrowUpCircle, Wallet } from "lucide-react"
import { api } from "@/lib/api"
import { cn, formatBRL, formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { FinancialAccount, FinancialMovement, CashCount } from "@/types"
import { CASH_COUNT_RESOLUTION_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { MoneyInput } from "@/components/MoneyInput"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const SOURCE_TYPE_LABELS: Record<string, string> = {
  payment:           "Pagamento",
  commission_payout: "Pagamento de comissão",
  manual:            "Lançamento manual",
  refund:            "Reembolso",
  subscription:      "Assinatura",
  package:           "Pacote",
  expense:           "Despesa",
  payable:           "Conta a pagar",
}

const EMERALD = "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300"
const DESTRUCTIVE = "bg-destructive/15 text-destructive border-destructive/30"

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

function isInflow(type: string): boolean {
  return type === "INFLOW" || type === "TRANSFER_IN"
}

function discrepancyClass(value: string): string {
  if (value.startsWith("-")) return "text-destructive"
  if (parseFloat(value) === 0) return "text-success"
  return "text-amber-600 dark:text-amber-400"
}

/* ----------------------- Tab: Movimentações do dia ----------------------- */
function MovementsTab() {
  const [movements, setMovements] = useState<FinancialMovement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const d = today()
      setMovements(await api.get<FinancialMovement[]>(`/financial/movements?date_from=${d}&date_to=${d}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const { inflow, outflow } = useMemo(() => {
    let i = 0, o = 0
    for (const m of movements) {
      const amt = parseFloat(m.amount) || 0
      if (isInflow(m.type)) i += amt; else o += amt
    }
    return { inflow: i, outflow: o }
  }, [movements])

  return (
    <div className="space-y-6">
      {/* KPI strip */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-5">
            <p className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              <ArrowDownCircle className="h-4 w-4 text-success" /> Entradas
            </p>
            <p className="mt-2 font-display text-3xl tracking-tight text-success">{formatBRL(inflow)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              <ArrowUpCircle className="h-4 w-4 text-destructive" /> Saídas
            </p>
            <p className="mt-2 font-display text-3xl tracking-tight text-destructive">{formatBRL(outflow)}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <p className="flex items-center gap-2 text-[11px] uppercase tracking-widest text-muted-foreground">
              <Wallet className="h-4 w-4" /> Saldo
            </p>
            <p className="mt-2 font-display text-3xl tracking-tight">{formatBRL(inflow - outflow)}</p>
          </CardContent>
        </Card>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : movements.length === 0 ? (
        <EmptyState title="Nenhuma movimentação hoje" description="As entradas e saídas do dia aparecem aqui." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Hora</th>
                <th className="px-4 py-3 text-left font-medium">Descrição</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {movements.map((m) => {
                const inflow = isInflow(m.type)
                return (
                  <tr key={m.movement_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 text-muted-foreground tabular-nums">
                      {new Date(m.occurred_at ?? m.created_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                    </td>
                    <td className="px-4 py-3">{SOURCE_TYPE_LABELS[m.source_type] ?? m.source_type}</td>
                    <td className="px-4 py-3">
                      <Badge variant="outline" className={cn("font-normal", inflow ? EMERALD : DESTRUCTIVE)}>
                        {inflow ? "Entrada" : "Saída"}
                      </Badge>
                    </td>
                    <td className={cn("px-4 py-3 text-right font-medium", inflow ? "text-success" : "text-destructive")}>
                      {inflow ? "+ " : "− "}{formatBRLFromDecimal(m.amount)}
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

/* ------------------------- Tab: Contagem de caixa ------------------------- */
function CashCountTab() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])
  const [counts, setCounts] = useState<CashCount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [accountId, setAccountId] = useState("")
  const [counted, setCounted] = useState("")
  const [resolution, setResolution] = useState("NO_ADJUSTMENT")
  const [notes, setNotes] = useState("")
  const [busy, setBusy] = useState(false)

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.account_id, a.name])), [accounts])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [accs, cnts] = await Promise.all([
        api.get<FinancialAccount[]>("/financial/accounts"),
        api.get<CashCount[]>("/financial/cash-counts"),
      ])
      setAccounts(accs)
      setCounts(cnts)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!accountId || !counted) return
    setBusy(true)
    try {
      await api.post("/financial/cash-counts", {
        account_id: accountId, counted_amount: counted, resolution, notes: notes || null,
      })
      toast.success("Contagem registrada")
      setAccountId(""); setCounted(""); setResolution("NO_ADJUSTMENT"); setNotes("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao registrar contagem")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="p-6">
          <form onSubmit={handleRegister} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1">
                <Label>Conta</Label>
                <Select value={accountId || "none"} onValueChange={(v) => v && setAccountId(v === "none" ? "" : v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue>{accountId ? (accountMap.get(accountId) ?? "—") : "Selecione"}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1">
                <Label htmlFor="cc-counted">Valor contado (R$)</Label>
                <MoneyInput id="cc-counted" value={counted} onChange={setCounted} />
              </div>
            </div>
            <div className="space-y-1.5">
              <Label>Resolução</Label>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="resolution" checked={resolution === "ADJUSTED"}
                    onChange={() => setResolution("ADJUSTED")} className="accent-primary" /> Com ajuste
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="resolution" checked={resolution === "NO_ADJUSTMENT"}
                    onChange={() => setResolution("NO_ADJUSTMENT")} className="accent-primary" /> Sem ajuste
                </label>
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="cc-notes">Observações</Label>
              <Textarea id="cc-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3}
                placeholder="Anotações sobre divergências, justificativas…" />
            </div>
            <Button type="submit" disabled={busy || !accountId || !counted}>
              {busy ? "Registrando…" : "Registrar"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : counts.length === 0 ? (
        <EmptyState title="Nenhuma contagem registrada" description="Registre a primeira contagem de caixa." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data/Hora</th>
                <th className="px-4 py-3 text-left font-medium">Conta</th>
                <th className="px-4 py-3 text-right font-medium">Esperado</th>
                <th className="px-4 py-3 text-right font-medium">Contado</th>
                <th className="px-4 py-3 text-right font-medium">Divergência</th>
                <th className="px-4 py-3 text-left font-medium">Resolução</th>
                <th className="px-4 py-3 text-left font-medium">Observações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {counts.map((c) => (
                <tr key={c.cash_count_id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(c.created_at)}</td>
                  <td className="px-4 py-3 font-medium">{accountMap.get(c.account_id) ?? "—"}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(c.expected_amount)}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(c.counted_amount)}</td>
                  <td className={cn("px-4 py-3 text-right font-medium", discrepancyClass(c.discrepancy))}>
                    {formatBRLFromDecimal(c.discrepancy)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{CASH_COUNT_RESOLUTION_LABELS[c.resolution] ?? c.resolution}</td>
                  <td className="px-4 py-3 text-muted-foreground">{c.notes ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

/* --------------------------------- Página --------------------------------- */
export default function CaixaPage() {
  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Caixa" description="Movimentações e contagem do dia." />
      <Tabs defaultValue="movimentacoes">
        <TabsList>
          <TabsTrigger value="movimentacoes">Movimentações do dia</TabsTrigger>
          <TabsTrigger value="contagem">Contagem de caixa</TabsTrigger>
        </TabsList>
        <TabsContent value="movimentacoes">
          <MovementsTab />
        </TabsContent>
        <TabsContent value="contagem">
          <CashCountTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
