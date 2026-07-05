"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import {
  Home,
  History,
  Ticket,
  Repeat,
  CircleUser,
  Tag,
  Package,
  ShieldCheck,
  CreditCard,
  LogOut,
  Loader2,
  type LucideIcon,
} from "lucide-react"
import { cn } from "@/lib/utils"
import {
  portal,
  clearPortalToken,
  setPortalAuthErrorHandler,
  PORTAL_TOKEN_KEY,
} from "@/lib/portal-api"
import type { PortalIdentity } from "@/lib/portal-types"
import { CompanyFilterProvider } from "@/context/CompanyFilterContext"
import { CompanyFilterBar } from "@/components/portal/CompanyFilterBar"

type NavLink = { title: string; url: string; icon: LucideIcon }

// Ordem espelha a screenshot: grupo principal + grupo de gestão de conta.
const PRIMARY: NavLink[] = [
  { title: "Início",      url: "/portal/dashboard",    icon: Home },
  { title: "Histórico",   url: "/portal/historico",    icon: History },
  { title: "Cotas",       url: "/portal/cotas",        icon: Ticket },
  { title: "Assinaturas", url: "/portal/assinaturas",  icon: Repeat },
  // TEMPORÁRIO (redesign F1): entradas mínimas para alcançar as telas novas.
  // A F4 reescreve a nav inteira — remover estas 2 linhas lá.
  { title: "Cupons",      url: "/portal/cupons",       icon: Tag },
  { title: "Produtos",    url: "/portal/produtos",     icon: Package },
  { title: "Perfil",      url: "/portal/perfil",       icon: CircleUser },
]
const SECONDARY: NavLink[] = [
  { title: "Consentimentos", url: "/portal/consentimentos", icon: ShieldCheck },
  { title: "Pagamentos",     url: "/portal/pagamentos",     icon: CreditCard },
]
const ALL_LINKS = [...PRIMARY, ...SECONDARY]

function isActive(pathname: string, url: string): boolean {
  return pathname === url || pathname.startsWith(url + "/")
}

function NavRow({
  link,
  active,
  onNavigate,
}: {
  link: NavLink
  active: boolean
  onNavigate?: () => void
}) {
  const Icon = link.icon
  return (
    <Link
      href={link.url}
      onClick={onNavigate}
      className={cn(
        "flex items-center gap-3 rounded-md px-3 py-2 transition-colors",
        active
          ? "bg-sidebar-accent text-sidebar-accent-foreground"
          : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
      )}
    >
      <Icon size={16} strokeWidth={1.5} className="flex-shrink-0 text-sidebar-primary" />
      <span className={cn("text-sm leading-tight", active && "font-medium")}>{link.title}</span>
    </Link>
  )
}

export default function PortalAppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const [ready, setReady] = useState(false)
  const [identity, setIdentity] = useState<PortalIdentity | null>(null)

  // Guard: sem portal_token → login. Também registra o handler de 401 do runtime.
  useEffect(() => {
    if (typeof window === "undefined") return
    const token = localStorage.getItem(PORTAL_TOKEN_KEY)
    if (!token) {
      router.replace("/portal/login")
      return
    }
    setPortalAuthErrorHandler(() => router.replace("/portal/login"))
    setReady(true)
    portal
      .get<PortalIdentity>("/portal/identity/me")
      .then(setIdentity)
      .catch(() => {
        /* 401 já tratado pelo portalFetch; outros erros não bloqueiam o shell */
      })
  }, [router])

  function logout() {
    clearPortalToken()
    router.replace("/portal/login")
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <CompanyFilterProvider>
    <div className="flex min-h-screen bg-background">
      {/* Nav lateral (md+) */}
      <aside className="hidden md:flex w-60 flex-shrink-0 flex-col border-r border-sidebar-border bg-sidebar">
        <div className="px-6 py-5">
          <span className="font-display block text-xl tracking-[0.3em] text-sidebar-primary leading-none">
            PALADINO
          </span>
          <span className="mt-1 block text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
            Portal do Cliente
          </span>
        </div>

        <nav className="flex-1 space-y-5 overflow-y-auto px-4 py-2">
          <div className="space-y-0.5">
            {PRIMARY.map((link) => (
              <NavRow key={link.url} link={link} active={isActive(pathname, link.url)} />
            ))}
          </div>
          <div className="space-y-0.5 border-t border-sidebar-border pt-4">
            {SECONDARY.map((link) => (
              <NavRow key={link.url} link={link} active={isActive(pathname, link.url)} />
            ))}
          </div>
        </nav>

        <div className="border-t border-sidebar-border px-6 py-4">
          <p className="truncate text-sm font-medium text-sidebar-foreground">
            {identity?.name ?? "Cliente"}
          </p>
          {identity?.email && (
            <p className="truncate text-xs text-muted-foreground">{identity.email}</p>
          )}
          <button
            onClick={logout}
            className="mt-3 flex items-center gap-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            <LogOut size={14} strokeWidth={1.5} /> Sair
          </button>
        </div>
      </aside>

      {/* Conteúdo */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar mobile com wordmark + sair */}
        <header className="flex items-center justify-between border-b border-border px-4 h-14 md:hidden">
          <div className="leading-none">
            <span className="font-display text-base tracking-[0.25em] text-primary">PALADINO</span>
          </div>
          <button
            onClick={logout}
            aria-label="Sair"
            className="flex items-center gap-1.5 text-sm text-muted-foreground"
          >
            <LogOut size={16} strokeWidth={1.5} /> Sair
          </button>
        </header>

        {/* F4a — menu de empresas, visível em todas as telas do grupo (app) */}
        <CompanyFilterBar />

        <main className="flex-1 px-4 py-6 pb-24 md:px-8 md:py-10 md:pb-10">
          <div className="mx-auto w-full max-w-3xl">{children}</div>
        </main>
      </div>

      {/* Bottom nav (mobile) */}
      <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-background md:hidden">
        {ALL_LINKS.map((link) => {
          const active = isActive(pathname, link.url)
          const Icon = link.icon
          return (
            <Link
              key={link.url}
              href={link.url}
              className={cn(
                "flex min-w-0 flex-1 flex-col items-center justify-center gap-0.5 py-2",
                active ? "text-primary" : "text-muted-foreground",
              )}
            >
              <Icon size={18} strokeWidth={1.5} />
              <span className="w-full truncate text-center text-[9px] leading-none">{link.title}</span>
            </Link>
          )
        })}
      </nav>
    </div>
    </CompanyFilterProvider>
  )
}
