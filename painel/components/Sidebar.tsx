"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const NAV_LINKS = [
  { href: "/dashboard",        label: "Agenda",           icon: "📅" },
  { href: "/appointments",     label: "Agendamentos",     icon: "🗓" },
  { href: "/customers",        label: "Clientes",         icon: "👥" },
  { href: "/services",         label: "Serviços",         icon: "✂️" },
  { href: "/professionals",    label: "Profissionais",    icon: "👤" },
  { href: "/products",         label: "Produtos",         icon: "📦" },
  { href: "/integrations",     label: "Integrações",      icon: "🔗" },
]

// ── Conteúdo do menu (reutilizado no desktop e no drawer mobile) ──────────────
function SidebarContent({
  pathname,
  logout,
  onNavigate,
}: {
  pathname: string
  logout: () => void
  onNavigate?: () => void
}) {
  return (
    <div className="flex flex-col h-full">
      <div className="px-6 py-5 border-b border-gray-100">
        <span className="text-xl font-bold tracking-tight">Paladino</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto">
        {NAV_LINKS.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            onClick={onNavigate}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors",
              pathname === href || (href !== "/dashboard" && pathname.startsWith(href))
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            <span style={{ fontSize: 15 }}>{icon}</span>
            {label}
          </Link>
        ))}
      </nav>

      <div className="px-4 py-4 border-t border-gray-100">
        <Button
          variant="ghost"
          className="w-full justify-start text-sm text-muted-foreground"
          onClick={logout}
        >
          Sair
        </Button>
      </div>
    </div>
  )
}

// ── Componente principal ──────────────────────────────────────────────────────
export default function Sidebar() {
  const pathname = usePathname()
  const { logout } = useAuth()
  const [open, setOpen] = useState(false)

  // Fecha o drawer ao mudar de rota
  useEffect(() => { setOpen(false) }, [pathname])

  // Impede scroll do body quando drawer está aberto
  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : ""
    return () => { document.body.style.overflow = "" }
  }, [open])

  return (
    <>
      {/* ── Desktop: sidebar fixa ─────────────────────────────────────────── */}
      <aside className="hidden lg:flex w-60 min-h-screen bg-white border-r flex-col shadow-sm flex-shrink-0">
        <SidebarContent pathname={pathname} logout={logout} />
      </aside>

      {/* ── Mobile: botão hamburguer ──────────────────────────────────────── */}
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "lg:hidden fixed top-4 left-4 z-40",
          "w-9 h-9 flex flex-col items-center justify-center gap-1.5 rounded-lg",
          "bg-white border border-gray-200 shadow-sm transition-opacity",
          open && "opacity-0 pointer-events-none",
        )}
        aria-label="Abrir menu"
      >
        <span className="w-4 h-0.5 bg-gray-600 rounded-full" />
        <span className="w-4 h-0.5 bg-gray-600 rounded-full" />
        <span className="w-4 h-0.5 bg-gray-600 rounded-full" />
      </button>

      {/* ── Mobile: overlay escuro ────────────────────────────────────────── */}
      {open && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* ── Mobile: drawer deslizante ─────────────────────────────────────── */}
      <aside
        className={cn(
          "lg:hidden fixed top-0 left-0 h-full w-72 z-50 bg-white shadow-xl",
          "transform transition-transform duration-300 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        {/* Botão fechar */}
        <button
          onClick={() => setOpen(false)}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-gray-100 text-gray-500 text-lg leading-none"
          aria-label="Fechar menu"
        >
          ×
        </button>

        <SidebarContent
          pathname={pathname}
          logout={logout}
          onNavigate={() => setOpen(false)}
        />
      </aside>
    </>
  )
}