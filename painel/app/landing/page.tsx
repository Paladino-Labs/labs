"use client"

import Link from "next/link"
import { Calendar, Users, CreditCard, BarChart3, Sun, Moon } from "lucide-react"
import type { LucideIcon } from "lucide-react"
import { useTheme } from "@/lib/theme"

const FEATURES: { icon: LucideIcon; title: string; desc: string }[] = [
  { icon: Calendar,   title: "Agenda inteligente", desc: "Calendário por profissional com slots automáticos." },
  { icon: Users,      title: "CRM completo",       desc: "Histórico, preferências e clientes em risco." },
  { icon: CreditCard, title: "Caixa e pagamentos", desc: "Cobranças, conciliação e fechamento diário." },
  { icon: BarChart3,  title: "Relatórios",         desc: "Receita, despesa, margem e comissões." },
]

export default function LandingPage() {
  const { theme, toggle } = useTheme()

  return (
    <div className="min-h-screen flex flex-col bg-background">
      {/* Header */}
      <header className="border-b border-border">
        <div className="mx-auto max-w-6xl flex items-center justify-between px-6 h-16">
          <span className="font-display text-xl tracking-[0.3em] text-primary">PALADINO</span>
          <div className="flex items-center gap-3">
            <button
              onClick={toggle}
              aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"}
              className="text-muted-foreground hover:text-foreground transition-colors p-2 rounded-md"
            >
              {theme === "dark" ? <Sun size={16} strokeWidth={1.5} /> : <Moon size={16} strokeWidth={1.5} />}
            </button>
            <Link
              href="/"
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:brightness-110 transition"
            >
              Entrar
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <span className="label-eyebrow">Plataforma multi-tenant</span>
          <h1 className="mt-6 font-display text-6xl md:text-7xl leading-[1.05] tracking-tight">
            Seu negócio,
            <br />
            no controle.
          </h1>
          <p className="mt-6 max-w-xl text-muted-foreground">
            Paladino é a plataforma para gerir negócios de serviço — agenda, equipe,
            caixa, operação e financeiro em um só lugar.
          </p>
          <Link
            href="/dashboard"
            className="mt-10 inline-flex rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:brightness-110 transition"
          >
            Acessar painel
          </Link>

          {/* Feature cards */}
          <div className="mt-20 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map(({ icon: Icon, title, desc }) => (
              <div key={title} className="rounded-md border border-border bg-card p-6">
                <Icon size={20} strokeWidth={1.5} className="text-primary" />
                <h3 className="mt-4 font-display text-xl">{title}</h3>
                <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
              </div>
            ))}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-border">
        <div className="mx-auto max-w-6xl px-6 py-6 text-xs text-muted-foreground">
          © {new Date().getFullYear()} Paladino. Todos os direitos reservados.
        </div>
      </footer>
    </div>
  )
}
