import Link from "next/link"
import {
  FileBarChart,
  BadgeDollarSign,
  Star,
  Boxes,
  ShieldCheck,
  Users,
  ChevronRight,
  BarChart3,
  type LucideIcon,
} from "lucide-react"
import { PageHeader } from "@/components/PageHeader"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent } from "@/components/ui/card"

type Report = {
  href: string
  icon: LucideIcon
  title: string
  description: string
}

const ACTIVE: Report[] = [
  { href: "/financeiro/dre", icon: FileBarChart,    title: "DRE",        description: "Demonstrativo de resultados do mês." },
  { href: "/comissoes",      icon: BadgeDollarSign, title: "Comissões",  description: "A pagar, pagas e por profissional." },
  { href: "/nps",            icon: Star,            title: "NPS",        description: "Satisfação e pesquisas respondidas." },
  { href: "/estoque",        icon: Boxes,           title: "Estoque",    description: "Quantidades e custo médio." },
  { href: "/audit",          icon: ShieldCheck,     title: "Auditoria",  description: "Trilha de ações sensíveis." },
  { href: "/crm",            icon: Users,           title: "CRM",        description: "Clientes em risco e classificações." },
]

const SOON: Omit<Report, "href">[] = [
  { icon: BarChart3, title: "Fluxo de caixa",            description: "Entradas e saídas com projeção." },
  { icon: BarChart3, title: "Performance por profissional", description: "Ranking e produtividade." },
  { icon: BarChart3, title: "Agendamentos por período",   description: "Picos e ocupação por horário." },
]

export default function RelatoriosPage() {
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Administração"
        title="Relatórios"
        description="Acesso rápido a indicadores e relatórios."
      />

      <section className="space-y-3">
        <h2 className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Disponíveis</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {ACTIVE.map((r) => (
            <Link key={r.href} href={r.href}>
              <Card className="h-full cursor-pointer transition-colors hover:border-primary">
                <CardContent className="flex items-center gap-4 p-5">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                    <r.icon size={20} strokeWidth={1.5} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="[font-family:var(--font-display)] text-lg leading-tight">{r.title}</p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">{r.description}</p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Em breve</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SOON.map((r) => (
            <Card key={r.title} className="h-full cursor-default opacity-60">
              <CardContent className="flex items-center gap-4 p-5">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-muted text-muted-foreground">
                  <r.icon size={20} strokeWidth={1.5} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="flex items-center gap-2 [font-family:var(--font-display)] text-lg leading-tight">
                    {r.title}
                    <Badge variant="outline" className="font-normal text-[10px]">Em breve</Badge>
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">{r.description}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>
    </div>
  )
}
