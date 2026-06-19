"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { ArrowRight, UserRound } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatDateTime } from "@/lib/utils"
import {
  type PortalDashboardResponse,
  type PortalIdentity,
  establishmentLabel,
} from "@/lib/portal-types"
import { AppointmentStatusBadge } from "@/components/portal/PortalStatusBadge"
import { QuotaProgress } from "@/components/portal/QuotaProgress"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

const TZ = "America/Sao_Paulo"

type Load = "loading" | "ok" | "error"

function SectionSkeleton({ rows }: { rows: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-16 w-full rounded-xl" />
      ))}
    </div>
  )
}

export default function PortalDashboardPage() {
  const [state, setState] = useState<Load>("loading")
  const [data, setData] = useState<PortalDashboardResponse | null>(null)
  const [identity, setIdentity] = useState<PortalIdentity | null>(null)

  function load() {
    setState("loading")
    portal
      .get<PortalDashboardResponse>("/portal/dashboard")
      .then((d) => {
        setData(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
    portal.get<PortalIdentity>("/portal/identity/me").then(setIdentity).catch(() => {})
  }, [])

  // Banner de upgrade: identidade "leve" → falta nome ou e-mail (heurística — §4).
  const showUpgrade = identity != null && (!identity.name || !identity.email)

  return (
    <div className="space-y-8">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Início</h1>

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

        {state === "loading" && <SectionSkeleton rows={3} />}
        {state === "error" && <ErrorState onRetry={load} />}
        {state === "ok" &&
          (data!.upcoming_appointments.length === 0 ? (
            <EmptyState message="Você ainda não tem agendamentos." />
          ) : (
            <div className="space-y-2">
              {data!.upcoming_appointments.slice(0, 5).map((a) => (
                <div
                  key={a.id}
                  className="flex items-start justify-between gap-3 rounded-xl bg-card px-4 py-3 ring-1 ring-foreground/10"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-foreground">
                      {a.service_names.join(" + ") || "Atendimento"}
                    </p>
                    <p className="truncate text-xs">
                      <span className="text-primary">{establishmentLabel(a)}</span>
                      {a.professional_name && (
                        <span className="text-muted-foreground"> · com {a.professional_name}</span>
                      )}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <span className="whitespace-nowrap text-xs text-muted-foreground">
                      {formatDateTime(a.start_at, TZ)}
                    </span>
                    <AppointmentStatusBadge status={a.status} />
                  </div>
                </div>
              ))}
            </div>
          ))}
      </section>

      {/* Cotas ativas */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl text-foreground">Cotas ativas</h2>
          <Link
            href="/portal/cotas"
            className="text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            Ver todas →
          </Link>
        </div>

        {state === "loading" && <SectionSkeleton rows={2} />}
        {state === "error" && <ErrorState onRetry={load} />}
        {state === "ok" &&
          (data!.active_credits.length === 0 ? (
            <EmptyState message="Nenhuma cota ativa." />
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {data!.active_credits.slice(0, 3).map((c) => (
                <div
                  key={c.credit_id}
                  className="rounded-xl bg-card p-4 ring-1 ring-foreground/10"
                >
                  <div className="flex items-start gap-2">
                    <UserRound size={14} strokeWidth={1.5} className="mt-0.5 text-primary" />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {c.service_name ?? c.entitlement_type}
                      </p>
                      <p className="truncate text-xs text-primary">{establishmentLabel(c)}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex items-center justify-between text-xs">
                    <span className="font-medium text-foreground">
                      {c.remaining_cotas} de {c.total_cotas} restantes
                    </span>
                    {c.expires_at && (
                      <span className="text-muted-foreground">
                        até {formatDateTime(c.expires_at, TZ).split(" ")[0]}
                      </span>
                    )}
                  </div>
                  <QuotaProgress
                    className="mt-2"
                    remaining={c.remaining_cotas}
                    total={c.total_cotas}
                  />
                </div>
              ))}
            </div>
          ))}
      </section>
    </div>
  )
}
