"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  AreaChart, Area, BarChart, Bar,
  CartesianGrid, Legend, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts"
import {
  ArrowLeftRight, BarChart2, ChevronRight,
  CreditCard, Minus, Percent, Plus, TrendingDown, TrendingUp,
} from "lucide-react"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

// ── Types ─────────────────────────────────────────────────────────────────────

interface Movement {
  id: string
  movement_type: "INFLOW" | "OUTFLOW" | string
  amount: number
  created_at: string
}

interface Payment {
  payment_id: string
  payment_method: string
  status: string
  created_at: string
}

type Period = 7 | 30 | 90

// ── Constants ─────────────────────────────────────────────────────────────────

const PERIOD_OPTIONS: { label: string; value: Period }[] = [
  { label: "7 dias",  value: 7  },
  { label: "30 dias", value: 30 },
  { label: "90 dias", value: 90 },
]

const METHOD_LABELS: Record<string, string> = {
  CASH:       "Dinheiro",
  PIX:        "PIX",
  MAQUININHA: "Maquininha",
  CREDIT:     "Crédito",
  DEBIT:      "Débito",
}

// Acesso rápido — cards compactos no final da página
const QUICK_LINKS = [
  {
    href:        "/financeiro/pagamentos",
    icon:        CreditCard,
    title:       "Pagamentos",
    description: "Visualize e confirme pagamentos de clientes",
  },
  {
    href:        "/financeiro/movimentacoes",
    icon:        ArrowLeftRight,
    title:       "Movimentações",
    description: "Entradas e saídas nas contas financeiras",
  },
  {
    href:        "/financeiro/pagamentos/novo",
    icon:        Plus,
    title:       "Registrar pagamento",
    description: "Registre um novo pagamento manualmente",
  },
  {
    href:        "/financeiro/taxas",
    icon:        Percent,
    title:       "Taxas de maquininha",
    description: "Configure as taxas por método de pagamento",
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function getDateFrom(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().split("T")[0]
}

/** Agrupa movements por dia (dd/MM) e devolve array ordenado crescente. */
function buildAreaData(movements: Movement[], days: number) {
  const map = new Map<string, { Entradas: number; Saídas: number }>()

  // Seed: todos os dias do período para não ter lacunas na linha
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date()
    d.setDate(d.getDate() - i)
    const key = d.toLocaleDateString("pt-BR", {
      day: "2-digit", month: "2-digit", timeZone: "America/Sao_Paulo",
    })
    map.set(key, { Entradas: 0, Saídas: 0 })
  }

  for (const m of movements) {
    const key = new Date(m.created_at).toLocaleDateString("pt-BR", {
      day: "2-digit", month: "2-digit", timeZone: "America/Sao_Paulo",
    })
    const entry = map.get(key)
    if (!entry) continue
    if (m.movement_type === "INFLOW") entry.Entradas += m.amount
    else                              entry.Saídas  += m.amount
  }

  return Array.from(map.entries()).map(([date, v]) => ({ date, ...v }))
}

/** Conta pagamentos confirmados por método de pagamento. */
function buildMethodData(payments: Payment[]) {
  const counts: Record<string, number> = {}
  for (const p of payments) {
    if (p.status !== "CONFIRMED" && p.status !== "PAID") continue
    const key = p.payment_method
    counts[key] = (counts[key] ?? 0) + 1
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1])
    .map(([method, count]) => ({
      method: METHOD_LABELS[method] ?? method,
      Pagamentos: count,
    }))
}

// ── Tooltip customizado ───────────────────────────────────────────────────────

interface TooltipPayload {
  name: string
  value: number
  color: string
}

function AreaTooltip({
  active, payload, label,
}: {
  active?: boolean
  payload?: TooltipPayload[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-foreground">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.name}: {formatBRL(p.value)}
        </p>
      ))}
    </div>
  )
}

function BarTooltip({
  active, payload, label,
}: {
  active?: boolean
  payload?: TooltipPayload[]
  label?: string
}) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-foreground">{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ color: p.color }}>
          {p.value} pagamento{p.value !== 1 ? "s" : ""}
        </p>
      ))}
    </div>
  )
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({
  label, value, hint, loading,
}: {
  label: string
  value: string
  hint?: string
  loading: boolean
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
        <p className="mt-2 font-display text-3xl tracking-tight">
          {loading ? <span className="text-muted-foreground">…</span> : value}
        </p>
        {hint && <p className="mt-1 text-xs italic text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function FinanceiroPage() {
  const [period, setPeriod]       = useState<Period>(30)
  const [movements, setMovements] = useState<Movement[]>([])
  const [payments,  setPayments]  = useState<Payment[]>([])
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    const dateFrom = getDateFrom(period)
    Promise.all([
      api.get<Movement[]>(`/financial/movements?date_from=${dateFrom}`),
      api.get<Payment[]>("/payments"),
    ])
      .then(([movs, pays]) => {
        setMovements(movs)
        setPayments(pays)
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [period])

  // ── KPI derivations ────────────────────────────────────────────────────────

  const totalInflow  = useMemo(() => movements.filter((m) => m.movement_type === "INFLOW" ).reduce((s, m) => s + m.amount, 0), [movements])
  const totalOutflow = useMemo(() => movements.filter((m) => m.movement_type === "OUTFLOW").reduce((s, m) => s + m.amount, 0), [movements])
  const netResult    = totalInflow - totalOutflow
  const txCount      = movements.length

  // ── Chart data ─────────────────────────────────────────────────────────────

  const areaData   = useMemo(() => buildAreaData(movements, period),  [movements, period])
  const methodData = useMemo(() => buildMethodData(payments),         [payments])

  // XAxis tick interval: show ~7 labels regardless of period
  const xInterval = period === 7 ? 0 : period === 30 ? 4 : 12

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">

      {/* Cabeçalho */}
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-3xl tracking-wide">Financeiro</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Visão geral das suas finanças
          </p>
        </div>

        {/* Seletor de período */}
        <div className="flex rounded-md border border-border overflow-hidden text-sm">
          {PERIOD_OPTIONS.map(({ label, value }) => (
            <button
              key={value}
              onClick={() => setPeriod(value)}
              className={
                period === value
                  ? "px-4 py-1.5 bg-primary text-primary-foreground font-medium"
                  : "px-4 py-1.5 text-muted-foreground hover:bg-accent transition-colors"
              }
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p className="text-sm text-destructive">
          Não foi possível carregar os dados: {error}
        </p>
      )}

      {/* ── KPI Cards ────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard
          label="Total de entradas"
          value={formatBRL(totalInflow)}
          hint={`últimos ${period} dias`}
          loading={loading}
        />
        <KpiCard
          label="Total de saídas"
          value={formatBRL(totalOutflow)}
          hint={`últimos ${period} dias`}
          loading={loading}
        />
        <Card>
          <CardContent className="p-5">
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground">
              Resultado líquido
            </p>
            <div className="mt-2 flex items-center gap-2">
              {!loading && (
                netResult >= 0
                  ? <TrendingUp className="h-5 w-5 text-success shrink-0" />
                  : <TrendingDown className="h-5 w-5 text-destructive shrink-0" />
              )}
              <p className={
                loading
                  ? "font-display text-3xl tracking-tight text-muted-foreground"
                  : netResult >= 0
                    ? "font-display text-3xl tracking-tight text-success"
                    : "font-display text-3xl tracking-tight text-destructive"
              }>
                {loading ? "…" : formatBRL(Math.abs(netResult))}
              </p>
            </div>
            {!loading && (
              <p className="mt-1 text-xs italic text-muted-foreground">
                {netResult >= 0 ? "superávit" : "déficit"}
              </p>
            )}
          </CardContent>
        </Card>
        <KpiCard
          label="Transações"
          value={loading ? "…" : String(txCount)}
          hint="movimentações no período"
          loading={loading}
        />
      </div>

      {/* ── Gráfico de área ───────────────────────────────────────────────────── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base font-medium">
            Entradas vs Saídas — últimos {period} dias
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!loading && movements.length === 0 ? (
            <div className="flex h-[300px] items-center justify-center">
              <p className="text-sm italic text-muted-foreground">
                Nenhuma movimentação registrada nos últimos {period} dias.
              </p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={300}>
              <AreaChart data={areaData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="gradInflow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--chart-1)" stopOpacity={0.35} />
                    <stop offset="95%" stopColor="var(--chart-1)" stopOpacity={0}    />
                  </linearGradient>
                  <linearGradient id="gradOutflow" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%"  stopColor="var(--chart-5)" stopOpacity={0.30} />
                    <stop offset="95%" stopColor="var(--chart-5)" stopOpacity={0}    />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                  interval={xInterval}
                />
                <YAxis
                  tickFormatter={(v: number) => formatBRL(v)}
                  tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                  width={72}
                />
                <Tooltip content={<AreaTooltip />} />
                <Legend
                  wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
                  iconType="circle"
                  iconSize={8}
                />
                <Area
                  type="monotone"
                  dataKey="Entradas"
                  stroke="var(--chart-1)"
                  fill="url(#gradInflow)"
                  strokeWidth={2}
                  dot={false}
                />
                <Area
                  type="monotone"
                  dataKey="Saídas"
                  stroke="var(--chart-5)"
                  fill="url(#gradOutflow)"
                  strokeWidth={2}
                  dot={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* ── Gráfico de métodos de pagamento ───────────────────────────────────── */}
      {methodData.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-medium flex items-center gap-2">
              <BarChart2 className="h-4 w-4 text-muted-foreground" />
              Métodos de pagamento
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart
                data={methodData}
                margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
                barSize={32}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis
                  dataKey="method"
                  tick={{ fontSize: 12, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                  axisLine={false}
                  tickLine={false}
                  width={32}
                />
                <Tooltip content={<BarTooltip />} />
                <Bar
                  dataKey="Pagamentos"
                  fill="var(--chart-2)"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* ── Acesso rápido ────────────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-xs uppercase tracking-widest text-muted-foreground">
          Acesso rápido
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_LINKS.map((s) => (
            <Link key={s.href} href={s.href}>
              <Card className="h-full cursor-pointer transition-colors hover:border-primary">
                <CardContent className="flex items-center gap-3 p-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                    <s.icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-tight">{s.title}</p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {s.description}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>

    </div>
  )
}
