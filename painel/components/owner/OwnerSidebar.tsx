"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"
import {
  MessagesSquare,
  LogOut,
  type LucideIcon,
} from "lucide-react"

type OwnerNavItem = {
  title: string
  url: string
  icon: LucideIcon
}

/**
 * ⚠️ O MENU FOI REDUZIDO DE PROPÓSITO — isto NÃO é descuido.
 *
 * Decisão do Silva (S-painel-telemetria): o painel de plataforma atual não é
 * útil, e a telemetria passa a ser a tela principal. As demais telas saíram
 * do menu, mas **continuam existindo e alcançáveis por URL**:
 *
 *   /owner/tenants · /owner/tenants/[id] · /owner/tenants/[id]/flags
 *   /owner/impersonation · /owner/sistema · /owner/settings · /owner/audit
 *
 * ⚠️ **Só a navegação mudou. Nenhuma rota, página ou endpoint foi removido.**
 * O backend `/platform/*` está intacto — inclusive o impersonation, que é o
 * caminho de dar suporte a um tenant, e pode haver função em uso que não é
 * óbvia.
 *
 * Isto cria deliberadamente o padrão "tela existe, caminho não existe" — que
 * este repo já tem em três ocorrências ACIDENTAIS (ver `/settings` órfão no
 * CLAUDE.md). Aqui é intencional e temporário: quando o painel definitivo for
 * desenhado, o Silva decide o que ressuscitar com base no que sentiu falta.
 * Não "conserte" restaurando os itens sem essa decisão.
 */
const NAV: OwnerNavItem[] = [
  { title: "Telemetria", url: "/owner/telemetria", icon: MessagesSquare },
]

function isActive(pathname: string, url: string): boolean {
  return pathname === url || pathname.startsWith(url + "/")
}

function SidebarContent({
  pathname,
  name,
  onLogout,
  onNavigate,
}: {
  pathname: string
  name: string | null
  onLogout: () => void
  onNavigate?: () => void
}) {
  return (
    <div className="flex h-full flex-col">
      {/* Identidade */}
      <div className="border-b border-sidebar-border px-6 py-5">
        <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">Plataforma</p>
        <span className="font-display text-xl tracking-[0.3em] text-sidebar-primary leading-none">
          PALADINO
        </span>
      </div>

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto px-4 py-5">
        <div className="space-y-0.5">
          {NAV.map((item) => {
            const active = isActive(pathname, item.url)
            const Icon = item.icon
            return (
              <Link
                key={item.url}
                href={item.url}
                onClick={onNavigate}
                className={cn(
                  "flex items-center gap-3 rounded-md px-3 py-2 transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                )}
              >
                <Icon size={16} strokeWidth={1.5} className="flex-shrink-0 text-sidebar-primary" />
                <span className={cn("font-display text-lg leading-tight", active && "italic")}>
                  {item.title}
                </span>
              </Link>
            )
          })}
        </div>
      </nav>

      {/* Rodapé */}
      <div className="border-t border-sidebar-border px-4 py-4">
        {name && (
          <p className="mb-2 truncate px-2 text-xs text-muted-foreground" title={name}>
            {name}
          </p>
        )}
        <button
          type="button"
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sidebar-foreground transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
        >
          <LogOut size={16} strokeWidth={1.5} className="flex-shrink-0 text-sidebar-primary" />
          <span className="font-display text-lg leading-tight">Sair</span>
        </button>
      </div>
    </div>
  )
}

export function OwnerSidebar() {
  const pathname = usePathname()
  const { name, logout } = useAuth()
  const [open, setOpen] = useState(false)

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setOpen(false) }, [pathname])

  return (
    <>
      {/* Desktop */}
      <aside className="hidden min-h-screen w-56 flex-shrink-0 flex-col border-r border-sidebar-border bg-sidebar shadow-sm lg:flex">
        <SidebarContent pathname={pathname} name={name} onLogout={logout} />
      </aside>

      {/* Mobile: hamburger */}
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "fixed top-4 left-4 z-40 flex h-9 w-9 flex-col items-center justify-center gap-1.5 rounded-lg",
          "border border-sidebar-border bg-sidebar shadow-sm transition-opacity lg:hidden",
          open && "pointer-events-none opacity-0",
        )}
        aria-label="Abrir menu"
      >
        <span className="h-0.5 w-4 rounded-full bg-sidebar-foreground" />
        <span className="h-0.5 w-4 rounded-full bg-sidebar-foreground" />
        <span className="h-0.5 w-4 rounded-full bg-sidebar-foreground" />
      </button>

      {/* Mobile: overlay + drawer */}
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={cn(
          "fixed top-0 left-0 z-50 h-full w-64 overflow-y-auto bg-sidebar shadow-xl lg:hidden",
          "transform transition-transform duration-300 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <SidebarContent pathname={pathname} name={name} onLogout={logout} onNavigate={() => setOpen(false)} />
      </aside>
    </>
  )
}
