"use client"

import { useMemo } from "react"
import {
  Calendar,
  DollarSign,
  Activity,
  AlertTriangle,
  Clock,
  Users,
  ListOrdered,
  MessageSquare,
  CreditCard,
  Landmark,
  Play,
  Pause,
  CircleDollarSign,
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
import { formatBRL } from "@/lib/utils"

function firstName(name: string | null, email: string | null): string {
  const raw = name?.split(" ")[0] ?? email?.split("@")[0]?.split(/[._]/)[0] ?? "Mestre"
  return raw.charAt(0).toUpperCase() + raw.slice(1).toLowerCase()
}

// ── Primitivos de layout ────────────────────────────────────────────────────
function PageHeader({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-col gap-2">
        <span className="label-eyebrow">{eyebrow}</span>
        <h1 className="font-display text-4xl md:text-5xl tracking-tight">{title}</h1>
      </div>
      <span className="text-[10px] uppercase tracking-[0.22em] text-muted-foreground border border-border rounded-sm px-2 py-1 whitespace-nowrap mt-2">
        Mock · Fase 0
      </span>
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

function KpiCard({ label, value, delta, icon: Icon }: { label: string; value: string; delta: string; icon: LucideIcon }) {
  return (
    <div className="bg-card px-7 py-6">
      <div className="flex items-center justify-between">
        <p className="text-[10px] uppercase tracking-[0.25em] text-primary/85">{label}</p>
        <Icon size={16} strokeWidth={1.5} className="text-muted-foreground" />
      </div>
      <p className="mt-3 font-display text-4xl leading-none tracking-tight">{value}</p>
      <p className="mt-3 text-xs italic text-muted-foreground">{delta}</p>
    </div>
  )
}

function KpiStrip({ items }: { items: { label: string; value: string; delta: string; icon: LucideIcon }[] }) {
  return (
    <section
      className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-3"
    >
      {items.map((k) => (
        <KpiCard key={k.label} {...k} />
      ))}
    </section>
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

// ── OWNER / ADMIN ───────────────────────────────────────────────────────────
const REVENUE_SERIES = [
  { month: "Out", receita: 18200, despesa: 11800 },
  { month: "Nov", receita: 19500, despesa: 12100 },
  { month: "Dez", receita: 24800, despesa: 14300 },
  { month: "Jan", receita: 21100, despesa: 13200 },
  { month: "Fev", receita: 22600, despesa: 13900 },
  { month: "Mar", receita: 24875, despesa: 14100 },
].map((d) => ({ ...d, margem: d.receita - d.despesa }))

function OwnerDashboard({ name }: { name: string }) {
  const kpis = [
    { label: "Agendamentos hoje", value: "28", delta: "+12% vs ontem", icon: Calendar },
    { label: "Faturamento do mês", value: formatBRL(2487.5), delta: "+8% vs mês anterior", icon: DollarSign },
    { label: "Ocupação", value: "76%", delta: "alta · saudável", icon: Activity },
  ]

  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Proprietário" title={`Olá, ${name}.`} />

      <KpiStrip items={kpis} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Receita × Despesa × Margem">
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={REVENUE_SERIES} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                <XAxis dataKey="month" stroke="var(--color-muted-foreground)" fontSize={12} tickLine={false} axisLine={false} />
                <YAxis
                  stroke="var(--color-muted-foreground)"
                  fontSize={12}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v) => `${(v as number) / 1000}k`}
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
                <Bar dataKey="receita" name="Receita" fill="var(--color-chart-1)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="despesa" name="Despesa" fill="var(--color-chart-2)" radius={[3, 3, 0, 0]} />
                <Bar dataKey="margem" name="Margem" fill="var(--color-chart-3)" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>

        <Panel title="Alertas" icon={AlertTriangle}>
          <BulletList
            tone="warning"
            items={[
              "3 pagamentos a confirmar",
              "2 itens com estoque baixo",
              "Promoção 'Verão' expira em 2 dias",
            ]}
          />
        </Panel>
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Panel title="Pendências" icon={Clock}>
          <BulletList
            items={[
              "2 payables vencendo nos próximos 7 dias",
              "Conciliação de caixa pendente (3 dias)",
              "1 fechamento de comissão aguardando",
            ]}
          />
        </Panel>

        <Panel title="CRM · clientes em risco" icon={Users}>
          <ul className="divide-y divide-border -my-1">
            {[
              { name: "Henrique Souza", days: 62 },
              { name: "Caio Albuquerque", days: 48 },
              { name: "Marcos Tavares", days: 41 },
            ].map((c) => (
              <li key={c.name} className="flex items-center justify-between py-2.5 text-sm">
                <span>{c.name}</span>
                <span className="text-xs italic text-muted-foreground">{c.days}d sem visita</span>
              </li>
            ))}
          </ul>
        </Panel>
      </section>
    </div>
  )
}

// ── OPERATOR ────────────────────────────────────────────────────────────────
function OperatorDashboard({ name }: { name: string }) {
  const kpis = [
    { label: "Agendamentos hoje", value: "28", delta: "5 ainda por vir", icon: Calendar },
    { label: "Na fila", value: "2", delta: "tempo médio 12 min", icon: ListOrdered },
    { label: "Caixa do dia", value: formatBRL(840), delta: "12 recebimentos", icon: Landmark },
  ]

  const agenda = [
    { hora: "09:00", cliente: "Bruno Lima", servico: "Corte + Barba" },
    { hora: "09:45", cliente: "Diego Antunes", servico: "Corte" },
    { hora: "10:30", cliente: "Felipe Castro", servico: "Barba" },
    { hora: "11:15", cliente: "Otávio Nunes", servico: "Corte + Sobrancelha" },
    { hora: "12:00", cliente: "Rafael Dias", servico: "Corte" },
  ]

  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Operação" title={`Bom turno, ${name}.`} />

      <KpiStrip items={kpis} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Agenda do dia" icon={Calendar}>
          <ul className="divide-y divide-border -my-1">
            {agenda.map((a) => (
              <li key={a.hora} className="grid grid-cols-[64px_1fr] items-center gap-3 py-2.5">
                <span className="font-display text-xl italic text-muted-foreground leading-none">{a.hora}</span>
                <div className="min-w-0">
                  <p className="font-display text-lg leading-tight">{a.cliente}</p>
                  <p className="text-xs italic text-muted-foreground">{a.servico}</p>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel title="Fila de espera" icon={ListOrdered}>
            <BulletList items={["Lucas Pereira · chegou 10:12", "Sérgio Mota · chegou 10:25"]} />
          </Panel>

          <Panel title="Atendimento humano" icon={MessageSquare}>
            <div className="flex items-center gap-2.5">
              <span className="h-2 w-2 rounded-full bg-warning" />
              <span className="text-sm">1 conversa em atendimento</span>
            </div>
          </Panel>

          <Panel title="Cobranças pendentes" icon={CreditCard}>
            <BulletList items={["Pedro Sales · " + formatBRL(70), "Igor Ramos · " + formatBRL(55)]} />
          </Panel>
        </div>
      </section>
    </div>
  )
}

// ── PROFESSIONAL ────────────────────────────────────────────────────────────
function ProfessionalDashboard({ name }: { name: string }) {
  const proximos = [
    { hora: "13:30", cliente: "André Souza", servico: "Corte + Barba" },
    { hora: "14:15", cliente: "Gustavo Reis", servico: "Corte" },
    { hora: "15:00", cliente: "Thiago Melo", servico: "Barba" },
  ]

  return (
    <div className="flex flex-col gap-8">
      <PageHeader eyebrow="Profissional" title={`Olá, ${name}.`} />

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">
        <Panel title="Próximos atendimentos" icon={Calendar}>
          <ul className="divide-y divide-border -my-1">
            {proximos.map((a) => (
              <li key={a.hora} className="grid grid-cols-[64px_1fr_auto] items-center gap-3 py-3">
                <span className="font-display text-xl italic text-muted-foreground leading-none">{a.hora}</span>
                <div className="min-w-0">
                  <p className="font-display text-lg leading-tight">{a.cliente}</p>
                  <p className="text-xs italic text-muted-foreground">{a.servico}</p>
                </div>
                <div className="flex items-center gap-2">
                  <button className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-accent/40 transition-colors">
                    <Play size={13} strokeWidth={1.5} /> Iniciar
                  </button>
                  <button className="flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1.5 text-xs hover:bg-accent/40 transition-colors">
                    <Pause size={13} strokeWidth={1.5} /> Pausar
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title="Comissões" icon={CircleDollarSign}>
          <p className="text-[10px] uppercase tracking-[0.25em] text-primary/85">Este mês</p>
          <p className="mt-2 font-display text-4xl leading-none tracking-tight">{formatBRL(340)}</p>
          <p className="mt-3 text-xs italic text-muted-foreground">extrato de comissões próprias</p>
        </Panel>
      </section>
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
