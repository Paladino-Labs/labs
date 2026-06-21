"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  Calendar,
  DollarSign,
  BarChart2,
  AlertTriangle,
  Clock,
  Users,
  ListOrdered,
  MessageSquare,
  CreditCard,
  Landmark,
  UserX,
} from "lucide-react"
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts"
import type { LucideIcon } from "lucide-react"
import { useAuth } from "@/context/AuthContext"
import { api } from "@/lib/api"
import { formatBRL, timeAgo } from "@/lib/utils"
import type {
  Appointment,
  Customer,
  Promotion,
  Payable,
  StockProduct,
  CashCount,
  DreResponse,
} from "@/types"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Skeleton } from "@/components/ui/skeleton"

// ── Tipos locais (não modelados em types/index.ts) ───────────────────────────
interface Payment {
  payment_id: string
  customer_id: string | null
  net_charged_amount: number
  status: string                       // PENDING | CONFIRMED | REFUNDED | ...
  created_at: string
}

interface CommissionPayout {
  payout_id: string
  status: string                       // PAID | PENDING | FAILED
}

interface WaitlistEntry {
  id: string
  customer_id: string
  status: string
  created_at?: string | null
}

interface Conversation {
  id: string
}

interface CrmAlertsResponse {
  at_risk_count: number
  at_risk_customers: { customer_id: string; days_since_last_visit: number | null }[]
  new_this_month: number
  vip_count: number
  recovered_this_week: number
}

interface ChartPoint {
  month: string
  receita: number
  despesa: number
  margem: number
}

function firstName(name: string | null, email: string | null): string {
  const raw = name?.split(" ")[0] ?? email?.split("@")[0]?.split(/[._]/)[0] ?? "Mestre"
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase()
}

// ── Helpers de data ──────────────────────────────────────────────────────────
function pad(n: number): string {
  return String(n).padStart(2, "0")
}

/** Início/fim do dia de hoje em ISO (UTC) — usado nos filtros de /appointments/. */
function todayStartISO(): string {
  const d = new Date(); d.setHours(0, 0, 0, 0); return d.toISOString()
}
function todayEndISO(): string {
  const d = new Date(); d.setHours(23, 59, 59, 999); return d.toISOString()
}
function todayApptParams(): string {
  const p = new URLSearchParams({
    start_after: todayStartISO(),
    start_before: todayEndISO(),
    page_size: "200",
  })
  return p.toString()
}

/**
 * Limites do mês como datetime LOCAL ("YYYY-MM-DDTHH:MM:SS", sem Z) — mesmo
 * padrão da tela /financeiro/dre. Evita o deslocamento de dia que toISOString()
 * causaria nas bordas do mês ao converter para UTC.
 */
function monthRefDate(offset: number): Date {
  const d = new Date()
  d.setDate(1)                       // antes de mexer no mês: evita overflow (31 → mês seguinte)
  d.setMonth(d.getMonth() - offset)
  return d
}
function monthStart(offset = 0): string {
  const d = monthRefDate(offset)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-01T00:00:00`
}
function monthEnd(offset = 0): string {
  const d = monthRefDate(offset)
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate()
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(last)}T23:59:59`
}
function monthLabel(offset = 0): string {
  const d = monthRefDate(offset)
  const s = d.toLocaleDateString("pt-BR", { month: "short" }).replace(".", "")
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function hourLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
}

// ── Primitivos de layout ────────────────────────────────────────────────────
function PageHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="flex flex-col gap-2">
      <span className="label-eyebrow">{eyebrow}</span>
      <h1 className="font-display text-4xl md:text-5xl tracking-tight">{title}</h1>
    </div>
  )
}

function Panel({ title, icon: Icon, children }: { title: string; icon?: LucideIcon; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-card">
      <div className="flex items-center gap-2 px-6 py-4 border-b border-border">
        {Icon && <Icon size={16} strokeWidth={1.5} className="text-primary" />}
        <h2 className="font-display text-2xl tracking-wide">{title}</h2>
      </div>
      <div className="px-6 py-5">{children}</div>
    </section>
  )
}

interface KpiItem {
  label: string
  value: string
  icon: LucideIcon
  href?: string          // se definido, o card é clicável
  delta?: string         // legenda secundária
}

function KpiCard({ label, value, icon: Icon, href, delta }: KpiItem) {
  const inner = (
    <div className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-6">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium uppercase tracking-widest text-muted-foreground">
          {label}
        </span>
        <Icon size={16} strokeWidth={1.5} className="text-muted-foreground" />
      </div>
      <span className="font-display text-4xl text-foreground">{value}</span>
      {delta && <span className="text-xs text-muted-foreground">{delta}</span>}
    </div>
  )

  if (href) {
    return (
      <Link
        href={href}
        className="block rounded-2xl transition-opacity hover:opacity-80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {inner}
      </Link>
    )
  }
  return inner
}

function KpiGrid({ items }: { items: KpiItem[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((k) => (
        <KpiCard key={k.label} {...k} />
      ))}
    </div>
  )
}

function BulletList({ items, tone = "default" }: { items: string[]; tone?: "default" | "warning" }) {
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item} className="flex items-start gap-2.5 text-sm">
          <span
            className={
              tone === "warning"
                ? "mt-1.5 h-1.5 w-1.5 rounded-full bg-warning flex-shrink-0"
                : "mt-1.5 h-1.5 w-1.5 rounded-full bg-primary/60 flex-shrink-0"
            }
          />
          <span>{item}</span>
        </li>
      ))}
    </ul>
  )
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return <p className="text-sm italic text-muted-foreground">{children}</p>
}

function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-8">
      <Skeleton className="h-14 w-72" />
      <Skeleton className="h-28 w-full" />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    </div>
  )
}

/**
 * Executa cada fetch isoladamente: nunca rejeita (retorna undefined em erro) e
 * contabiliza sucessos para o caller decidir se houve falha TOTAL.
 */
function makeGuard(counter: { ok: number; total: number }) {
  return async function guard<T>(fn: () => Promise<T>): Promise<T | undefined> {
    counter.total++
    try {
      const r = await fn()
      counter.ok++
      return r
    } catch {
      return undefined
    }
  }
}

const REVENUE_BARS = [
  { key: "receita", name: "Receita", color: "var(--color-chart-1)" },
  { key: "despesa", name: "Despesa", color: "var(--color-chart-2)" },
  { key: "margem", name: "Margem", color: "var(--color-chart-3)" },
]

function RevenueChart({ series }: { series: ChartPoint[] }) {
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={series} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
          <XAxis dataKey="month" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
          <YAxis
            stroke="var(--color-muted-foreground)"
            fontSize={12}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v) => `${Math.round((v as number) / 1000)}k`}
          />
          <Tooltip
            cursor={{ fill: "var(--color-muted)", opacity: 0.3 }}
            contentStyle={{
              background: "var(--color-popover)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 12,
            }}
            formatter={(value) => formatBRL(Number(value))}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {REVENUE_BARS.map((b) => (
            <Bar key={b.key} dataKey={b.key} name={b.name} fill={b.color} radius={[3, 3, 0, 0]} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

// ── OWNER / ADMIN ─────────────────────────────────────────────────────────────
function OwnerDashboard({ name }: { name: string }) {
  const [loading, setLoading] = useState(true)
  const [fatal, setFatal] = useState(false)

  const [apptsToday, setApptsToday] = useState<number | null>(null)
  const [revenueMonth, setRevenueMonth] = useState<number | null>(null)
  const [series, setSeries] = useState<ChartPoint[] | null>(null)
  const [alerts, setAlerts] = useState<string[]>([])
  const [pendings, setPendings] = useState<string[]>([])
  const [atRisk, setAtRisk] = useState<{ name: string; days: number | null }[] | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setFatal(false)
    const counter = { ok: 0, total: 0 }
    const guard = makeGuard(counter)

    const [appts, dreSeries, payments, stock, promos, payables, cashCounts, payouts, crm, customers] =
      await Promise.all([
        guard(() => api.get<Appointment[]>(`/appointments/?${todayApptParams()}`)),
        guard(() =>
          Promise.all(
            [5, 4, 3, 2, 1, 0].map((offset) =>
              api
                .get<DreResponse>(`/financial/dre?date_from=${monthStart(offset)}&date_to=${monthEnd(offset)}`)
                .then((d) => ({
                  month: monthLabel(offset),
                  receita: Number(d.receita_total),
                  despesa: Number(d.despesa_total),
                  margem: Number(d.resultado_liquido),
                })),
            ),
          ),
        ),
        guard(() => api.get<Payment[]>("/payments")),
        guard(() => api.get<StockProduct[]>("/stock/?active_only=true")),
        guard(() => api.get<Promotion[]>("/promotions")),
        guard(() => api.get<Payable[]>("/payables/")),
        guard(() => api.get<CashCount[]>("/financial/cash-counts")),
        guard(() => api.get<CommissionPayout[]>("/commission-payouts")),
        guard(() => api.get<CrmAlertsResponse>("/crm/alerts")),
        guard(() => api.get<Customer[]>("/customers/")),
      ])

    setApptsToday(appts ? appts.length : null)

    if (dreSeries) {
      setSeries(dreSeries)
      setRevenueMonth(dreSeries[dreSeries.length - 1]?.receita ?? null)
    } else {
      setSeries(null)
      setRevenueMonth(null)
    }

    // Alertas
    const a: string[] = []
    if (payments) {
      const n = payments.filter((p) => p.status === "PENDING").length
      if (n) a.push(`${n} pagamento(s) a confirmar`)
    }
    if (stock) {
      const n = stock.filter(
        (i) => i.stock != null && i.stock_min_alert != null && i.stock <= Number(i.stock_min_alert),
      ).length
      if (n) a.push(`${n} item(ns) com estoque baixo`)
    }
    if (promos) {
      const soon = new Date(); soon.setDate(soon.getDate() + 7)
      const n = promos.filter(
        (p) => p.valid_until && new Date(p.valid_until) <= soon && p.status === "ACTIVE",
      ).length
      if (n) a.push(`${n} promoção(ões) expirando em 7 dias`)
    }
    setAlerts(a)

    // Pendências
    const pend: string[] = []
    if (payables) {
      const wk = new Date(); wk.setDate(wk.getDate() + 7)
      const n = payables.filter(
        (p) => p.due_date && new Date(p.due_date) <= wk && p.status !== "PAID" && p.status !== "CANCELLED",
      ).length
      if (n) pend.push(`${n} conta(s) a pagar vencendo em 7 dias`)
    }
    if (cashCounts) {
      const todayStr = new Date().toDateString()
      const countedToday = cashCounts.some((c) => new Date(c.created_at).toDateString() === todayStr)
      if (!countedToday) pend.push("Caixa do dia ainda não conferido")
    }
    if (payouts) {
      const n = payouts.filter((p) => p.status !== "PAID").length
      if (n) pend.push(`${n} fechamento(s) de comissão pendente(s)`)
    }
    setPendings(pend)

    // CRM — resolve nome via mapa de clientes (a resposta só traz customer_id)
    if (crm) {
      const nameMap = new Map((customers ?? []).map((c) => [c.id, c.name]))
      setAtRisk(
        crm.at_risk_customers.map((c) => ({
          name: nameMap.get(c.customer_id) ?? "Cliente",
          days: c.days_since_last_visit ?? null,
        })),
      )
    } else {
      setAtRisk(null)
    }

    setFatal(counter.ok === 0)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  if (loading) return <DashboardSkeleton />
  if (fatal) {
    return (
      <div className="flex flex-col gap-8">
        <PageHeader eyebrow="Proprietário" title={`Olá, ${name}.`} />
        <ErrorState message="Não foi possível carregar o painel." onRetry={load} />
      </div>
    )
  }

  const kpis: KpiItem[] = [
    {
      label: "Agendamentos hoje",
      value: apptsToday == null ? "—" : String(apptsToday),
      icon: Calendar,
      href: "/appointments",
      delta: "atendimentos",
    },
    {
      label: "Faturamento do mês",
      value: revenueMonth == null ? "—" : formatBRL(revenueMonth),
      icon: DollarSign,
      href: "/financeiro",
      delta: "receita bruta",
    },
    {
      label: "Ocupação",
      value: "—",
      icon: BarChart2,
      // sem href — sem endpoint de capacidade
      delta: "em breve",
    },
  ]

  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Proprietário" title={`Olá, ${name}.`} />

      <KpiGrid items={kpis} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Receita × Despesa × Margem">
          {series ? (
            <RevenueChart series={series} />
          ) : (
            <div className="flex h-72 items-center justify-center">
              <EmptyHint>Não foi possível carregar a série financeira.</EmptyHint>
            </div>
          )}
        </Panel>

        <Panel title="Alertas" icon={AlertTriangle}>
          {alerts.length ? (
            <BulletList tone="warning" items={alerts} />
          ) : (
            <EmptyHint>Nenhum alerta no momento.</EmptyHint>
          )}
        </Panel>
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Pendências" icon={Clock}>
          {pendings.length ? (
            <BulletList items={pendings} />
          ) : (
            <EmptyHint>Sem pendências.</EmptyHint>
          )}
        </Panel>

        <Panel title="CRM · clientes em risco" icon={Users}>
          {atRisk == null ? (
            <EmptyHint>Não foi possível carregar o CRM.</EmptyHint>
          ) : atRisk.length === 0 ? (
            <EmptyHint>Nenhum cliente em risco.</EmptyHint>
          ) : (
            <ul className="divide-y divide-border -my-1">
              {atRisk.map((c, i) => (
                <li key={`${c.name}-${i}`} className="flex items-center justify-between py-2.5 text-sm">
                  <span>{c.name}</span>
                  <span className="text-xs italic text-muted-foreground">
                    {c.days == null ? "—" : `${c.days}d sem visita`}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </section>
    </div>
  )
}

// ── OPERATOR ────────────────────────────────────────────────────────────────
function OperatorDashboard({ name }: { name: string }) {
  const [loading, setLoading] = useState(true)
  const [fatal, setFatal] = useState(false)

  const [appts, setAppts] = useState<Appointment[] | null>(null)
  const [naFila, setNaFila] = useState<number | null>(null)
  const [queue, setQueue] = useState<WaitlistEntry[] | null>(null)
  const [atendimento, setAtendimento] = useState<number | null>(null)
  const [payments, setPayments] = useState<Payment[] | null>(null)
  const [nameMap, setNameMap] = useState<Map<string, string>>(new Map())

  const load = useCallback(async () => {
    setLoading(true); setFatal(false)
    const counter = { ok: 0, total: 0 }
    const guard = makeGuard(counter)

    const [apptsRes, queueRes, convsRes, paymentsRes, customers] = await Promise.all([
      guard(() => api.get<Appointment[]>(`/appointments/?${todayApptParams()}`)),
      guard(() => api.get<WaitlistEntry[]>("/waitlist/entries")),
      guard(() => api.get<Conversation[]>("/conversations")),
      guard(() => api.get<Payment[]>("/payments")),
      guard(() => api.get<Customer[]>("/customers/")),
    ])

    setAppts(apptsRes ?? null)
    setQueue(queueRes ?? null)
    setNaFila(queueRes ? queueRes.length : null)
    setAtendimento(convsRes ? convsRes.length : null)
    setPayments(paymentsRes ?? null)
    setNameMap(new Map((customers ?? []).map((c) => [c.id, c.name])))

    setFatal(counter.ok === 0)
    setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])

  const agenda = useMemo(
    () =>
      (appts ?? [])
        .slice()
        .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())
        .slice(0, 5),
    [appts],
  )

  const todayConfirmed = useMemo(() => {
    const todayStr = new Date().toDateString()
    return (payments ?? []).filter(
      (p) => p.status === "CONFIRMED" && new Date(p.created_at).toDateString() === todayStr,
    )
  }, [payments])

  const caixaDia = useMemo(
    () => todayConfirmed.reduce((s, p) => s + Number(p.net_charged_amount), 0),
    [todayConfirmed],
  )

  const pendingPayments = useMemo(
    () => (payments ?? []).filter((p) => p.status === "PENDING"),
    [payments],
  )

  if (loading) return <DashboardSkeleton />
  if (fatal) {
    return (
      <div className="flex flex-col gap-8">
        <PageHeader eyebrow="Operação" title={`Bom turno, ${name}.`} />
        <ErrorState message="Não foi possível carregar o painel." onRetry={load} />
      </div>
    )
  }

  const kpis: KpiItem[] = [
    {
      label: "Agendamentos hoje",
      value: appts == null ? "—" : String(appts.length),
      icon: Calendar,
      href: "/appointments",
      delta: "no dia de hoje",
    },
    {
      label: "Na fila",
      value: naFila == null ? "—" : String(naFila),
      icon: ListOrdered,
      href: "/fila",
      delta: "clientes aguardando",
    },
    {
      label: "Caixa do dia",
      value: payments == null ? "—" : formatBRL(caixaDia),
      icon: Landmark,
      href: "/caixa",
      delta: `${todayConfirmed.length} recebimento(s)`,
    },
  ]

  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Operação" title={`Bom turno, ${name}.`} />

      <KpiGrid items={kpis} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Agenda do dia" icon={Calendar}>
          {appts == null ? (
            <EmptyHint>Não foi possível carregar a agenda.</EmptyHint>
          ) : agenda.length === 0 ? (
            <EmptyHint>Nenhum atendimento hoje.</EmptyHint>
          ) : (
            <ul className="divide-y divide-border -my-1">
              {agenda.map((a) => (
                <li key={a.id} className="grid grid-cols-[64px_1fr] items-center gap-3 py-2.5">
                  <span className="font-display text-xl italic text-muted-foreground leading-none">
                    {hourLabel(a.start_at)}
                  </span>
                  <div className="min-w-0">
                    <p className="font-display text-lg leading-tight">{a.customer?.name ?? "Cliente"}</p>
                    <p className="text-xs italic text-muted-foreground">
                      {a.services.map((s) => s.service_name).join(", ") || "—"}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel title="Fila de espera" icon={ListOrdered}>
            {queue == null ? (
              <EmptyHint>Não foi possível carregar a fila.</EmptyHint>
            ) : queue.length === 0 ? (
              <EmptyHint>Fila vazia.</EmptyHint>
            ) : (
              <BulletList
                items={queue
                  .slice(0, 5)
                  .map((e) => `${nameMap.get(e.customer_id) ?? "Cliente"} · ${timeAgo(e.created_at)}`)}
              />
            )}
          </Panel>

          <Panel title="Atendimento humano" icon={MessageSquare}>
            {atendimento == null ? (
              <EmptyHint>Não foi possível carregar.</EmptyHint>
            ) : (
              <div className="flex items-center gap-2.5">
                <span className={`h-2 w-2 rounded-full ${atendimento > 0 ? "bg-warning" : "bg-primary/40"}`} />
                <span className="text-sm">
                  {atendimento === 0
                    ? "Nenhuma conversa em atendimento"
                    : `${atendimento} conversa(s) em atendimento`}
                </span>
              </div>
            )}
          </Panel>

          <Panel title="Cobranças pendentes" icon={CreditCard}>
            {payments == null ? (
              <EmptyHint>Não foi possível carregar.</EmptyHint>
            ) : pendingPayments.length === 0 ? (
              <EmptyHint>Nenhuma cobrança pendente.</EmptyHint>
            ) : (
              <BulletList
                items={pendingPayments
                  .slice(0, 5)
                  .map(
                    (p) =>
                      `${nameMap.get(p.customer_id ?? "") ?? "Cliente"} · ${formatBRL(p.net_charged_amount)}`,
                  )}
              />
            )}
          </Panel>
        </div>
      </section>
    </div>
  )
}

// ── PROFESSIONAL ──────────────────────────────────────────────────────────────
// ⛔ GAP DE BACKEND: não há vínculo User → Professional.
// O JWT e GET /auth/me expõem apenas { id, email, name, company_id, role } — sem
// professional_id. O modelo Professional também não tem user_id. Sem esse
// vínculo é impossível filtrar agendamentos/comissões do profissional logado.
// TODO(backend): expor professional_id em /auth/me (ou criar User.professional_id)
// para então ligar "Próximos atendimentos" (GET /appointments/ + filtro client-side)
// e "Comissões do mês" (GET /commissions?professional_id=...).
function ProfessionalDashboard({ name }: { name: string }) {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Profissional" title={`Olá, ${name}.`} />
      <EmptyState
        icon={<UserX size={28} strokeWidth={1.5} />}
        title="Perfil profissional não vinculado"
        description="Seu usuário ainda não está associado a um cadastro de profissional. Assim que o vínculo existir, seus próximos atendimentos e comissões aparecerão aqui."
      />
    </div>
  )
}

export default function DashboardPage() {
  const { name, email, role } = useAuth()
  const fname = useMemo(() => firstName(name, email), [name, email])

  if (role === "PROFESSIONAL") return <ProfessionalDashboard name={fname} />
  if (role === "OPERATOR") return <OperatorDashboard name={fname} />
  // OWNER / ADMIN (e fallback)
  return <OwnerDashboard name={fname} />
}
