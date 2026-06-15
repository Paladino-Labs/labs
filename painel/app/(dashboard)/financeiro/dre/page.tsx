"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  BarChart, Bar, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts"
import { BarChart3 } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRL, formatBRLFromDecimal } from "@/lib/utils"
import type { DreResponse } from "@/types"
import { ENTRY_CATEGORY_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { DateTimePicker } from "@/components/DateTimePicker"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"

type PeriodMode = "month" | "quarter" | "year" | "custom"

function pad(n: number) { return String(n).padStart(2, "0") }
function startOf(y: number, m: number, d: number) { return `${y}-${pad(m)}-${pad(d)}T00:00:00` }
function endOf(y: number, m: number, d: number) { return `${y}-${pad(m)}-${pad(d)}T23:59:59` }
function lastDay(y: number, m: number) { return new Date(y, m, 0).getDate() }

function rangeFor(mode: PeriodMode): { from: string; to: string } {
  const now = new Date()
  const y = now.getFullYear()
  const m = now.getMonth() + 1
  if (mode === "month") return { from: startOf(y, m, 1), to: endOf(y, m, lastDay(y, m)) }
  if (mode === "quarter") {
    const qStart = Math.floor((m - 1) / 3) * 3 + 1
    const qEnd = qStart + 2
    return { from: startOf(y, qStart, 1), to: endOf(y, qEnd, lastDay(y, qEnd)) }
  }
  return { from: startOf(y, 1, 1), to: endOf(y, 12, 31) } // year
}

const PERIOD_TABS: { label: string; value: PeriodMode }[] = [
  { label: "Mês", value: "month" },
  { label: "Trimestre", value: "quarter" },
  { label: "Ano", value: "year" },
  { label: "Custom", value: "custom" },
]

interface TooltipPayload { name: string; value: number; color: string }
function ChartTooltip({ active, payload, label }: { active?: boolean; payload?: TooltipPayload[]; label?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-foreground">{label}</p>
      {payload.map((p) => <p key={p.name} style={{ color: p.color }}>{formatBRL(p.value)}</p>)}
    </div>
  )
}

function BucketTable({ title, data, total }: { title: string; data: Record<string, string>; total: string }) {
  const rows = Object.entries(data ?? {})
  return (
    <Card>
      <CardHeader className="pb-2"><CardTitle className="font-display text-xl tracking-wide">{title}</CardTitle></CardHeader>
      <CardContent className="p-0">
        <table className="w-full text-sm">
          <thead className="text-muted-foreground border-b border-border">
            <tr>
              <th className="px-4 py-2 text-left font-medium">Categoria</th>
              <th className="px-4 py-2 text-right font-medium">Valor</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.length === 0 ? (
              <tr><td colSpan={2} className="px-4 py-3 text-center text-xs italic text-muted-foreground">Sem lançamentos</td></tr>
            ) : rows.map(([cat, val]) => (
              <tr key={cat}>
                <td className="px-4 py-2 text-muted-foreground">{ENTRY_CATEGORY_LABELS[cat] ?? cat}</td>
                <td className="px-4 py-2 text-right">{formatBRLFromDecimal(val)}</td>
              </tr>
            ))}
            <tr className="border-t border-border">
              <td className="px-4 py-2 font-medium">Total</td>
              <td className="px-4 py-2 text-right font-medium">{formatBRLFromDecimal(total)}</td>
            </tr>
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}

export default function DrePage() {
  const [mode, setMode] = useState<PeriodMode>("month")
  const [customFrom, setCustomFrom] = useState("")
  const [customTo, setCustomTo] = useState("")
  const [dre, setDre] = useState<DreResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    let from: string, to: string
    if (mode === "custom") {
      if (!customFrom || !customTo) { setLoading(false); return }
      from = `${customFrom}:00`
      to = `${customTo}:00`
    } else {
      const r = rangeFor(mode)
      from = r.from; to = r.to
    }
    setLoading(true); setError(null)
    try {
      const params = new URLSearchParams({ date_from: from, date_to: to })
      setDre(await api.get<DreResponse>(`/financial/dre?${params.toString()}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [mode, customFrom, customTo])

  useEffect(() => { load() }, [load])

  // Composição do gráfico (apresentação): barras conforme screenshot.
  // Os *_total já vêm somados da API; aqui só agrupamos as saídas numa barra.
  const chartData = useMemo(() => {
    if (!dre) return []
    const saidas = ["custo_total", "despesa_total", "taxa_total", "comissao_total", "estorno_total"]
      .reduce((s, k) => s + (parseFloat((dre as unknown as Record<string, string>)[k]) || 0), 0)
    return [
      { name: "Receita", value: parseFloat(dre.receita_total) || 0 },
      { name: "Custo+Despesa+Taxa+Comissão+Estorno", value: saidas },
      { name: "Resultado líquido", value: parseFloat(dre.resultado_liquido) || 0 },
    ]
  }, [dre])

  const liquidoNegative = dre?.resultado_liquido.startsWith("-")

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="DRE" description="Demonstrativo de resultados por período." />

      {/* Seletor de período */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="flex rounded-md border border-border overflow-hidden text-sm">
          {PERIOD_TABS.map(({ label, value }) => (
            <button key={value} onClick={() => setMode(value)}
              className={mode === value
                ? "px-4 py-1.5 bg-primary text-primary-foreground font-medium"
                : "px-4 py-1.5 text-muted-foreground hover:bg-accent transition-colors"}>
              {label}
            </button>
          ))}
        </div>
        {mode === "custom" && (
          <>
            <div className="space-y-1">
              <Label htmlFor="dre-from">De</Label>
              <DateTimePicker id="dre-from" value={customFrom} onChange={setCustomFrom} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="dre-to">Até</Label>
              <DateTimePicker id="dre-to" value={customTo} onChange={setCustomTo} />
            </div>
            <Button onClick={load} disabled={!customFrom || !customTo}>Gerar</Button>
          </>
        )}
      </div>

      {loading ? (
        <Skeleton className="h-96 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !dre ? (
        <p className="text-sm text-muted-foreground">Selecione um intervalo personalizado e clique em Gerar.</p>
      ) : (
        <>
          {/* KPI strip */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Card><CardContent className="p-5">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Receita total</p>
              <p className="mt-2 font-display text-3xl tracking-tight">{formatBRLFromDecimal(dre.receita_total)}</p>
            </CardContent></Card>
            <Card><CardContent className="p-5">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Custo total</p>
              <p className="mt-2 font-display text-3xl tracking-tight">{formatBRLFromDecimal(dre.custo_total)}</p>
            </CardContent></Card>
            <Card><CardContent className="p-5">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Despesa total</p>
              <p className="mt-2 font-display text-3xl tracking-tight">{formatBRLFromDecimal(dre.despesa_total)}</p>
            </CardContent></Card>
            <Card><CardContent className="p-5">
              <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Resultado líquido</p>
              <p className={`mt-2 font-display text-3xl tracking-tight ${liquidoNegative ? "text-destructive" : "text-success"}`}>
                {formatBRLFromDecimal(dre.resultado_liquido)}
              </p>
            </CardContent></Card>
          </div>

          {/* Gráfico */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base font-medium flex items-center gap-2">
                <BarChart3 className="h-4 w-4 text-muted-foreground" /> Receita × Saídas × Resultado
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }} barSize={120}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                  <XAxis dataKey="name" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} />
                  <YAxis tickFormatter={(v: number) => formatBRL(v)} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} axisLine={false} tickLine={false} width={80} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--muted)", opacity: 0.3 }} />
                  <Bar dataKey="value" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>

          {/* Tabelas por bucket */}
          <div className="grid gap-4 lg:grid-cols-2">
            <BucketTable title="Receita" data={dre.receita} total={dre.receita_total} />
            <BucketTable title="Custo" data={dre.custo} total={dre.custo_total} />
            <BucketTable title="Despesa" data={dre.despesa} total={dre.despesa_total} />
            <BucketTable title="Taxa" data={dre.taxa} total={dre.taxa_total} />
            <BucketTable title="Comissão" data={dre.comissao} total={dre.comissao_total} />
            <BucketTable title="Estorno" data={dre.estorno} total={dre.estorno_total} />
            <BucketTable title="Ajuste" data={dre.ajuste} total={dre.ajuste_total} />
          </div>

          {/* Resultado */}
          <Card>
            <CardContent className="space-y-2 p-5">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Resultado bruto</span>
                <span className="font-medium">{formatBRLFromDecimal(dre.resultado_bruto)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Resultado líquido</span>
                <span className={`font-display text-2xl tracking-tight ${liquidoNegative ? "text-destructive" : "text-success"}`}>
                  {formatBRLFromDecimal(dre.resultado_liquido)}
                </span>
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  )
}
