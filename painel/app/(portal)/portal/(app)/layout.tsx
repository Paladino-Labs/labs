"use client"
// Redesign F4b — chrome novo do portal: header (wordmark + tema + avatar
// dropdown) + CompanyFilterBar. Navegação vira hub → blocos → seções
// (sidebar e bottom-nav antigas removidas; seções têm "‹ Voltar").

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { CircleUser, Loader2, LogOut } from "lucide-react"
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
import { ThemeToggle } from "@/components/booking/ThemeToggle"

function initials(name: string | null | undefined, email: string | null | undefined): string {
  const source = name?.trim()
  if (source) {
    const parts = source.split(/\s+/)
    const first = parts[0]?.[0] ?? ""
    const last = parts.length > 1 ? parts[parts.length - 1][0] : ""
    return (first + last).toUpperCase() || "C"
  }
  return email?.[0]?.toUpperCase() ?? "C"
}

function AvatarMenu({
  identity,
  onLogout,
}: {
  identity: PortalIdentity | null
  onLogout: () => void
}) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)

  // Fecha ao clicar fora (não há DropdownMenu shadcn no projeto).
  useEffect(() => {
    if (!open) return
    function onPointerDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener("mousedown", onPointerDown)
    return () => document.removeEventListener("mousedown", onPointerDown)
  }, [open])

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Menu do cliente"
        aria-expanded={open}
        className={cn(
          "flex h-9 w-9 items-center justify-center rounded-full border border-border bg-card text-xs font-medium tracking-wide text-foreground transition-colors hover:border-primary/40",
          open && "border-primary/60",
        )}
      >
        {initials(identity?.name, identity?.email)}
      </button>

      {open && (
        <div className="absolute right-0 top-11 z-50 w-60 overflow-hidden rounded-xl border border-border bg-card shadow-lg">
          <div className="border-b border-border px-4 py-3">
            <p className="truncate text-sm font-medium text-foreground">
              {identity?.name ?? "Cliente"}
            </p>
            {identity?.email && (
              <p className="truncate text-xs text-muted-foreground">{identity.email}</p>
            )}
          </div>
          <div className="p-1">
            <Link
              href="/portal/perfil"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent"
            >
              <CircleUser size={15} strokeWidth={1.5} className="text-muted-foreground" />
              Perfil
            </Link>
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                onLogout()
              }}
              className="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10"
            >
              <LogOut size={15} strokeWidth={1.5} />
              Sair
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default function PortalAppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter()
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
      <div className="flex min-h-screen flex-col bg-background">
        <header className="flex h-14 items-center justify-between border-b border-border px-4 md:px-8">
          <Link href="/portal/dashboard" className="leading-none">
            <span className="font-display text-lg tracking-[0.3em] text-primary md:text-xl">
              PALADINO
            </span>
          </Link>
          <div className="flex items-center gap-2">
            <ThemeToggle />
            <AvatarMenu identity={identity} onLogout={logout} />
          </div>
        </header>

        {/* F4a — menu de empresas, visível em todas as telas do grupo (app) */}
        <CompanyFilterBar />

        <main className="flex-1 px-4 py-6 md:px-8 md:py-10">
          <div className="mx-auto w-full max-w-5xl">{children}</div>
        </main>
      </div>
    </CompanyFilterProvider>
  )
}
