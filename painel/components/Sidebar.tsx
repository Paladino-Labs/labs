"use client"

import { useState, useEffect } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { cn } from "@/lib/utils"
import {
  LayoutDashboard,
  CalendarDays,
  Users,
  Scissors,
  UserCircle,
  Package,
  Settings,
  Link2,
  UserCog,
  LogOut,
  Sun,
  Moon,
} from "lucide-react"
import Image from "next/image"
import { useTheme } from "@/lib/theme"

const NAV_LINKS = [
  { href: "/dashboard",        label: "Início",            icon: LayoutDashboard, roles: null },
  { href: "/appointments",     label: "Agendamentos",      icon: CalendarDays,    roles: null },
  { href: "/customers",        label: "Clientes",          icon: Users,           roles: null },
  { href: "/services",         label: "Serviços",          icon: Scissors,        roles: null },
  { href: "/professionals",    label: "Barbeiros",         icon: UserCircle,      roles: null },
  { href: "/products",         label: "Produtos",          icon: Package,         roles: null },
  { href: "/integrations",     label: "Integrações",       icon: Link2,           roles: null },
  { href: "/users",            label: "Usuários",          icon: UserCog,         roles: ["OWNER", "ADMIN", "PLATFORM_OWNER"] },
  { href: "/settings",         label: "Configurações",     icon: Settings,        roles: null },
]

function getInitials(email: string | null): string {
  if (!email) return "P"
  const name = email.split("@")[0]
  const parts = name.split(/[._-]/)
  return parts
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("")
}

function SidebarContent({
  pathname,
  email,
  role,
  logout,
  onNavigate,
}: {
  pathname: string
  email: string | null
  role: string | null
  logout: () => void
  onNavigate?: () => void
}) {
  const initials = getInitials(email)
  const displayName = email?.split("@")[0]?.replace(/[._]/g, " ") ?? "Usuário"
  const { theme, toggle } = useTheme()

  return (
    <div className="flex flex-col h-full">

      {/* Logo */}
      <div className="px-6 py-5 border-b border-sidebar-border">
        <Image
          src="/paladino-wordmark.png"
          alt="Paladino"
          width={120}
          height={32}
          className="h-8 w-auto object-contain"
          priority
        />
      </div>

      {/* Nav */}
      <nav className="flex-1 px-4 py-5 overflow-y-auto">
        <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground mb-3 px-2">
          Navegação
        </p>
        <div className="space-y-0.5">
          {NAV_LINKS.filter(({ roles }) => !roles || roles.includes(role ?? "")).map(({ href, label, icon: Icon }) => {
            const active =
              pathname === href ||
              (href !== "/dashboard" && pathname.startsWith(href))
            return (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                className={cn(
                  "flex items-center justify-between rounded-md px-3 py-2 transition-colors",
                  active
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
                )}
              >
                <span className="flex items-center gap-3">
                  <Icon
                    size={16}
                    strokeWidth={1.5}
                    className="flex-shrink-0 text-sidebar-primary"
                  />
                  <span
                    className={cn(
                      "font-display text-lg leading-tight",
                      active && "italic"
                    )}
                  >
                    {label}
                  </span>
                </span>
                {active && (
                  <span className="text-[10px] text-sidebar-primary leading-none">
                    ◆
                  </span>
                )}
              </Link>
            )
          })}
        </div>
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-sidebar-border space-y-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded-full border border-sidebar-border bg-sidebar-accent flex items-center justify-center flex-shrink-0">
            <span className="font-display text-sm text-sidebar-primary leading-none">
              {initials}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="font-display text-sm text-sidebar-foreground truncate capitalize">
              {displayName}
            </p>
            <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
              {role ?? "admin"}
            </p>
          </div>
          <button
            onClick={logout}
            aria-label="Sair"
            className="text-muted-foreground hover:text-sidebar-foreground transition-colors p-1 rounded"
          >
            <LogOut size={15} strokeWidth={1.5} />
          </button>
        </div>

        <button
          onClick={toggle}
          className="flex items-center gap-2 text-xs text-muted-foreground hover:text-sidebar-foreground transition-colors w-full px-1"
          aria-label={theme === "dark" ? "Ativar tema claro" : "Ativar tema escuro"}
        >
          {theme === "dark" ? (
            <Sun size={13} strokeWidth={1.5} />
          ) : (
            <Moon size={13} strokeWidth={1.5} />
          )}
          <span>{theme === "dark" ? "Tema claro" : "Tema escuro"}</span>
        </button>
      </div>

    </div>
  )
}

export default function Sidebar() {
  const pathname = usePathname()
  const { email, role, logout } = useAuth()
  const [open, setOpen] = useState(false)

  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { setOpen(false) }, [pathname])

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : ""
    return () => { document.body.style.overflow = "" }
  }, [open])

  const contentProps = { pathname, email, role, logout }

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden lg:flex w-60 min-h-screen bg-sidebar border-r border-sidebar-border flex-col shadow-sm flex-shrink-0">
        <SidebarContent {...contentProps} />
      </aside>

      {/* Mobile: hamburger */}
      <button
        onClick={() => setOpen(true)}
        className={cn(
          "lg:hidden fixed top-4 left-4 z-40",
          "w-9 h-9 flex flex-col items-center justify-center gap-1.5 rounded-lg",
          "bg-sidebar border border-sidebar-border shadow-sm transition-opacity",
          open && "opacity-0 pointer-events-none",
        )}
        aria-label="Abrir menu"
      >
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
        <span className="w-4 h-0.5 bg-sidebar-foreground rounded-full" />
      </button>

      {/* Mobile: overlay */}
      {open && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={() => setOpen(false)}
        />
      )}

      {/* Mobile: drawer */}
      <aside
        className={cn(
          "lg:hidden fixed top-0 left-0 h-full w-72 z-50 bg-sidebar shadow-xl",
          "transform transition-transform duration-300 ease-in-out",
          open ? "translate-x-0" : "-translate-x-full",
        )}
      >
        <button
          onClick={() => setOpen(false)}
          className="absolute top-4 right-4 w-8 h-8 flex items-center justify-center rounded-lg hover:bg-sidebar-accent text-sidebar-foreground text-lg leading-none"
          aria-label="Fechar menu"
        >
          ×
        </button>
        <SidebarContent {...contentProps} onNavigate={() => setOpen(false)} />
      </aside>
    </>
  )
}
