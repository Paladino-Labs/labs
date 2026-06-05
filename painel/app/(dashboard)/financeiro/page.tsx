"use client"

import Link from "next/link"
import { CreditCard, ArrowLeftRight, Plus, ChevronRight } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"

const sections = [
  {
    href: "/financeiro/pagamentos",
    icon: CreditCard,
    title: "Pagamentos",
    description: "Visualize e confirme pagamentos de clientes",
  },
  {
    href: "/financeiro/movimentacoes",
    icon: ArrowLeftRight,
    title: "Movimentações",
    description: "Entradas e saídas nas contas financeiras",
  },
  {
    href: "/financeiro/pagamentos/novo",
    icon: Plus,
    title: "Registrar pagamento",
    description: "Registre um novo pagamento manualmente",
  },
]

export default function FinanceiroPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="font-display text-3xl tracking-wide">Financeiro</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Gerencie pagamentos e movimentações financeiras
        </p>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {sections.map((s) => (
          <Link key={s.href} href={s.href}>
            <Card className="h-full cursor-pointer transition-colors hover:border-primary">
              <CardContent className="flex items-start gap-4 p-6">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                  <s.icon className="h-5 w-5" />
                </div>
                <div className="flex-1">
                  <p className="[font-family:var(--font-display)] text-lg">{s.title}</p>
                  <p className="mt-1 text-xs text-muted-foreground">{s.description}</p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  )
}
