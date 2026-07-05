"use client"
// Redesign F4b — home hub do portal: saudação, próximos agendamentos
// (1 card por empresa em "Todas"), CTA de empresa filtrada e grid
// "Sua conta" com resumos (counts do GET /portal/dashboard — 1 request).

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  ArrowRight,
  ChevronRight,
  CreditCard,
  History,
  Package,
  Repeat,
  RefreshCw,
  Tag,
  Ticket,
  type LucideIcon,
} from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatDateTime } from "@/lib/utils"
import {
  type PortalAppointmentItem,
  type PortalDashboardResponse,
  type PortalIdentity,
  establishmentLabel,
} from "@/lib/portal-types"
import { useCompanyFilter } from "@/context/CompanyFilterContext"
import { AppointmentStatusBadge } from "@/components/portal/PortalStatusBadge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

const TZ = "America/Sao_Paulo"

type Load = "loading" | "ok" | "error"

/** 1 card por empresa: o agendamento futuro mais próximo de cada uma. */
function earliestPerCompany(items: PortalAppointmentItem[]): PortalAppointmentItem[] {
  const byCompany = new Map<string, PortalAppointmentItem>()
  for (const a of items) {
    const current = byCompany.get(a.company_id)
    if (!current || a.start_at < current.start_at) byCompany.set(a.company_id, a)
  }
  return [...byCompany.values()].sort((a, b) => a.start_at.localeCompare(b.start_at))
}

function plural(n: number, singular: string, pluralForm: string): string {
  return `${n} ${n === 1 ? singular : pluralForm}`
}

function AccountBlock({
  href,
  icon: Icon,
  title,
  summary,
}: {
  href: string
  icon: LucideIcon
  title: string
  summary: string
}) {
  return (
    <Link
      href={href}
      className="group flex flex-col gap-4 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-card/80 hover:ring-primary/30"
    >
      <div className="flex items-start justify-between">
        <Icon size={18} strokeWidth={1.5} className="text-primary" />
        <ChevronRight
          size={16}
          strokeWidth={1.5}
          className="text-muted-foreground transition-colors group-hover:text-primary"
        />
      </div>
      <div>
        <p className="font-display text-lg text-foreground">{title}</p>
        <p className="text-xs text-muted-foreground">{summary}</p>
      </div>
    </Link>
  )
}

export default function PortalDashboardPage() {
  const router = useRouter()
  const { selectedCompanyId, selectedCompany } = useCompanyFilter()
  const [state, setState] = useState<Load>("loading")
  const [data, setData] = useState<PortalDashboardResponse | null>(null)
  const [identity, setIdentity] = useState<PortalIdentity | null>(null)

  const filtered = selectedCompanyId != null

  const load = useCallback(() => {
    setState("loading")
    const q = selectedCompanyId ? `?company_id=${selectedCompanyId}` : ""
    portal
      .get<PortalDashboardResponse>(`/portal/dashboard${q}`)
      .then((d) => {
        setData(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }, [selectedCompanyId])

  useEffect(() => {
    load()
  }, [load])

  useEffect(() => {
    portal.get<PortalIdentity>("/portal/identity/me").then(setIdentity).catch(() => {})
  }, [])

  const firstName = identity?.name?.trim().split(/\s+/)[0] ?? null
  // Banner de upgrade: identidade "leve" → falta nome ou e-mail (heurística — §4).
  const showUpgrade = identity != null && (!identity.name || !identity.email)

  const upcomingCards = useMemo(
    () => (data ? earliestPerCompany(data.upcoming_appointments) : []),
    [data],
  )

  const counts = data?.counts
  const blocks = data
    ? [
        {
          href: "/portal/cotas",
          icon: Ticket,
          title: "Cotas",
          summary: plural(data.active_credits.length, "ativa", "ativas"),
        },
        {
          href: "/portal/assinaturas",
          icon: Repeat,
          title: "Assinaturas",
          summary: plural(data.active_subscriptions.length, "ativa", "ativas"),
        },
        {
          href: "/portal/produtos",
          icon: Package,
          title: "Produtos",
          summary: counts
            ? plural(counts.reserved_products, "reservado", "reservados")
            : "ver produtos",
        },
        {
          href: "/portal/cupons",
          icon: Tag,
          title: "Cupons",
          summary: counts
            ? plural(counts.coupons, "disponível", "disponíveis")
            : "ver cupons",
        },
        {
          href: "/portal/historico",
          icon: History,
          title: "Histórico",
          summary: "agendamentos passados",
        },
        {
          href: "/portal/pagamentos",
          icon: CreditCard,
          title: "Pagamentos",
          summary: counts
            ? plural(counts.payments, "lançamento", "lançamentos")
            : "ver pagamentos",
        },
      ]
    : []

  return (
    <div className="space-y-8">
      {/* Cabeçalho */}
      <div className="space-y-1">
        <p className="text-[10px] uppercase tracking-[0.25em] text-muted-foreground">
          Portal do Cliente
        </p>
        <h1 className="font-display text-4xl tracking-wide text-foreground">
          {firstName ? `Olá, ${firstName}` : "Olá"}
        </h1>
        {filtered && selectedCompany && (
          <p className="text-sm text-muted-foreground">
            Filtrando por <span className="text-primary">{selectedCompany.company_name}</span>
          </p>
        )}
      </div>

      {showUpgrade && (
        <Link
          href="/portal/perfil"
          className="flex items-center justify-between gap-3 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 transition-colors hover:bg-primary/10"
        >
          <div>
            <p className="text-sm font-medium text-foreground">Complete seu perfil</p>
            <p className="text-xs text-muted-foreground">
              Adicione seu nome e e-mail para uma experiência completa.
            </p>
          </div>
          <ArrowRight size={16} strokeWidth={1.5} className="flex-shrink-0 text-primary" />
        </Link>
      )}

      {/* CTA da empresa filtrada */}
      {filtered && selectedCompany && (
        <div className="space-y-3 rounded-xl bg-card p-5 ring-1 ring-foreground/10">
          <p className="text-[10px] uppercase tracking-[0.25em] text-primary">
            {selectedCompany.company_name}
          </p>
          <p className="font-display text-xl text-foreground">Quer agendar ou comprar?</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => router.push(`/book/${selectedCompany.slug}/agendar`)}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Agendar horário
            </button>
            <button
              type="button"
              onClick={() => router.push(`/book/${selectedCompany.slug}`)}
              className="rounded-md border border-border px-4 py-2 text-sm text-foreground transition-colors hover:bg-accent"
            >
              Ver catálogo
            </button>
          </div>
        </div>
      )}

      {/* Próximos agendamentos */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl text-foreground">Próximos agendamentos</h2>
          <Link
            href="/portal/historico"
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Ver histórico →
          </Link>
        </div>

        {state === "loading" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Skeleton className="h-28 w-full rounded-xl" />
            <Skeleton className="h-28 w-full rounded-xl" />
          </div>
        )}
        {state === "error" && <ErrorState onRetry={load} />}
        {state === "ok" &&
          (upcomingCards.length === 0 ? (
            <EmptyState
              message={
                filtered
                  ? "Nenhum agendamento futuro nesta empresa."
                  : "Nenhum agendamento futuro."
              }
            />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {upcomingCards.map((a) => (
                // F2 — card leva ao detalhe (cancelar/remarcar ficam lá)
                <Link
                  key={a.id}
                  href={`/portal/agendamento/${a.id}`}
                  className="group flex flex-col gap-3 rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-card/80 hover:ring-primary/30"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {a.service_names.join(" + ") || "Atendimento"}
                      </p>
                      {a.professional_name && (
                        <p className="truncate text-xs text-muted-foreground">
                          com {a.professional_name}
                        </p>
                      )}
                    </div>
                    <AppointmentStatusBadge status={a.status} />
                  </div>
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-primary">{formatDateTime(a.start_at, TZ)}</span>
                    <ChevronRight
                      size={14}
                      strokeWidth={1.5}
                      className="text-muted-foreground transition-colors group-hover:text-primary"
                    />
                  </div>
                  {!filtered && (
                    <p className="border-t border-border/60 pt-2 text-[10px] uppercase tracking-[0.2em] text-muted-foreground">
                      {establishmentLabel(a)}
                    </p>
                  )}
                </Link>
              ))}
            </div>
          ))}
      </section>

      {/* Sua conta */}
      <section className="space-y-3">
        <h2 className="font-display text-xl text-foreground">Sua conta</h2>
        {state === "loading" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-28 w-full rounded-xl" />
            ))}
          </div>
        )}
        {state === "error" && <ErrorState onRetry={load} />}
        {state === "ok" && (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {blocks.map((b) => (
              <AccountBlock key={b.href} {...b} />
            ))}
          </div>
        )}
      </section>

      {state === "ok" && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <RefreshCw size={12} strokeWidth={1.5} /> Dados atualizados agora
        </p>
      )}
    </div>
  )
}
