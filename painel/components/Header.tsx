"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter, usePathname } from "next/navigation"
import { Sun, Moon, LogOut } from "lucide-react"
import { useAuth, ROLE_LABELS, type Role } from "@/context/AuthContext"
import { useTheme } from "@/lib/theme"
import { api } from "@/lib/api"
import { cn } from "@/lib/utils"
import RoleDevSelector from "@/components/RoleDevSelector"

const BREADCRUMB_MAP: Record<string, string> = {
  dashboard:     "Dashboard",
  agenda:        "Agenda",
  appointments:  "Operações",
  fila:          "Fila",
  inbox:         "Atendimento humano",
  customers:     "Clientes",
  comunicacao:   "Comunicação",
  logs:          "Histórico",
  catalogo:      "Catálogo",
  servicos:      "Serviços",
  produtos:      "Produtos",
  categorias:    "Categorias",
  pacotes:       "Pacotes",
  compras:       "Vendas",
  assinaturas:   "Assinaturas",
  planos:        "Planos",
  promocoes:     "Promoções",
  cupons:        "Cupons",
  financeiro:    "Financeiro",
  pagamentos:    "Pagamentos",
  conciliacao:   "Conciliação",
  dre:           "DRE",
  contas:        "Contas",
  extrato:       "Extrato",
  taxas:         "Taxas",
  despesas:      "Despesas",
  estoque:       "Estoque / Fornecedores",
  payables:      "Contas a pagar",
  comissoes:     "Comissões",
  professionals: "Profissionais",
  settings:      "Configurações",
  usuarios:      "Usuários e acessos",
  audit:         "Auditoria",
}

function labelFor(segment: string): string {
  return BREADCRUMB_MAP[segment] ?? segment.charAt(0).toUpperCase() + segment.slice(1)
}

function getInitials(name: string | null, email: string | null): string {
  const source = name?.trim() || email?.split("@")[0]?.replace(/[._-]/g, " ") || ""
  if (!source) return "P"
  const parts = source.split(/\s+/).filter(Boolean)
  return parts.slice(0, 2).map((p) => p[0]?.toUpperCase() ?? "").join("") || "P"
}

export default function Header() {
  const router = useRouter()
  const pathname = usePathname()
  const { name, email, role, logout } = useAuth()
  const { theme, toggle } = useTheme()

  // Nome real da empresa (substitui o mock da Fase 0).
  const [tenantName, setTenantName] = useState<string | null>(null)
  useEffect(() => {
    api.get<{ name: string }>("/companies/me")
      .then((c) => setTenantName(c.name))
      .catch(() => {})
  }, [])

  const segments = pathname.split("/").filter(Boolean)
  const crumbs = segments.map((seg, i) => ({
    label: labelFor(seg),
    href: "/" + segments.slice(0, i + 1).join("/"),
  }))

  const initials = getInitials(name, email)
  const roleLabel = role ? ROLE_LABELS[role as Role] ?? role : null

  function handleLogout() {
    logout()
    router.push("/")
  }

  return (
    <header className="border-b border-border bg-background/80 backdrop-blur sticky top-0 z-30">
      {/* Linha 1 */}
      <div className="flex items-center gap-4 px-4 pl-16 lg:pl-6 h-14">
        <div className="flex flex-col leading-tight min-w-0">
          <span className="font-display text-xl leading-none truncate">{tenantName ?? ""}</span>
        </div>

        <div className="flex-1" />

        <RoleDevSelector />

        <button
          onClick={toggle}
          aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"}
          title={theme === "dark" ? "Tema claro" : "Tema escuro"}
          className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-md"
        >
          {theme === "dark" ? <Sun size={16} strokeWidth={1.5} /> : <Moon size={16} strokeWidth={1.5} />}
        </button>

        <div className="flex items-center gap-2.5">
          <div className="flex flex-col items-end leading-tight">
            {name && <span className="text-sm leading-none truncate max-w-[140px]">{name}</span>}
            {roleLabel && (
              <span className="text-xs text-muted-foreground leading-none mt-0.5">{roleLabel}</span>
            )}
          </div>
          <div
            title={name ?? email ?? undefined}
            className="h-9 w-9 rounded-full bg-accent flex items-center justify-center flex-shrink-0"
          >
            <span className="font-display text-sm text-accent-foreground leading-none">{initials}</span>
          </div>
        </div>

        <button
          onClick={handleLogout}
          aria-label="Sair"
          title="Sair"
          className="text-muted-foreground hover:text-foreground transition-colors p-1.5 rounded-md"
        >
          <LogOut size={16} strokeWidth={1.5} />
        </button>
      </div>

      {/* Linha 2 — breadcrumbs */}
      {crumbs.length > 0 && (
        <nav className="flex items-center gap-1.5 px-4 pl-16 lg:pl-6 pb-2 text-xs text-muted-foreground">
          <Link href="/dashboard" className="hover:text-foreground transition-colors">
            Início
          </Link>
          {crumbs.map((c, i) => (
            <span key={c.href} className="flex items-center gap-1.5">
              <span className="text-muted-foreground/50">›</span>
              {i === crumbs.length - 1 ? (
                <span className={cn("text-foreground")}>{c.label}</span>
              ) : (
                <Link href={c.href} className="hover:text-foreground transition-colors">
                  {c.label}
                </Link>
              )}
            </span>
          ))}
        </nav>
      )}
    </header>
  )
}
