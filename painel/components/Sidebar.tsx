"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

const NAV_LINKS = [
  { href: "/dashboard",         label: "Agenda" },
  { href: "/appointments",      label: "Agendamentos" },
  { href: "/appointments/new",  label: "Novo Agendamento" },
  { href: "/customers",         label: "Clientes" },
  { href: "/services",          label: "Serviços" },
  { href: "/professionals",     label: "Profissionais" },
  { href: "/integrations",      label: "Integrações" },
]

export default function Sidebar() {
  const pathname = usePathname()
  const { logout } = useAuth()

  return (
    <aside className="w-60 min-h-screen bg-white border-r flex flex-col shadow-sm">
      <div className="px-6 py-5 border-b">
        <span className="text-xl font-bold tracking-tight">Paladino</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "block rounded-md px-3 py-2 text-sm font-medium transition-colors",
              pathname === href
                ? "bg-primary text-primary-foreground"
                : "text-muted-foreground hover:bg-muted hover:text-foreground"
            )}
          >
            {label}
          </Link>
        ))}
      </nav>

      <div className="px-4 py-4 border-t">
        <Button variant="ghost" className="w-full justify-start text-sm" onClick={logout}>
          Sair
        </Button>
      </div>
    </aside>
  )
}
