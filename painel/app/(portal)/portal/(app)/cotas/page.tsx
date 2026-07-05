"use client"

import { useCallback, useEffect, useState } from "react"
import { ChevronDown } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatDateShort, formatDateTime } from "@/lib/utils"
import {
  type PortalCreditItem,
  type CreditConsumptionItem,
  establishmentLabel,
} from "@/lib/portal-types"
import { useCompanyFilter } from "@/context/CompanyFilterContext"
import { CreditStatusBadge } from "@/components/portal/PortalStatusBadge"
import { QuotaProgress } from "@/components/portal/QuotaProgress"
import { cn } from "@/lib/utils"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"

function isExpired(c: PortalCreditItem): boolean {
  if (c.status === "EXPIRED") return true
  if (!c.expires_at) return false
  return new Date(c.expires_at).getTime() < Date.now()
}

function CreditCard({ credit, showCompany }: { credit: PortalCreditItem; showCompany: boolean }) {
  const [open, setOpen] = useState(false)
  // B3 — histórico de consumo carregado de forma lazy ao expandir.
  const [consumptions, setConsumptions] = useState<CreditConsumptionItem[] | null>(null)
  const [loadingConsumptions, setLoadingConsumptions] = useState(false)
  const expired = isExpired(credit)

  useEffect(() => {
    if (!open || consumptions !== null) return
    setLoadingConsumptions(true)
    portal
      .get<CreditConsumptionItem[]>(`/portal/credits/${credit.credit_id}/consumptions`)
      .then((data) => setConsumptions(data))
      .catch(() => setConsumptions([])) // em erro, lista vazia
      .finally(() => setLoadingConsumptions(false))
  }, [open, credit.credit_id, consumptions])

  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">
            {credit.service_name ?? credit.entitlement_type}
          </p>
          {showCompany && (
            <p className="truncate text-xs text-primary">{establishmentLabel(credit)}</p>
          )}
        </div>
        <CreditStatusBadge status={credit.status} />
      </div>

      <div className="mt-3 flex items-center justify-between text-xs">
        <span className="font-medium text-foreground">
          {credit.remaining_cotas} de {credit.total_cotas} restantes
        </span>
        {credit.expires_at && (
          <span className={cn(expired ? "text-destructive" : "text-muted-foreground")}>
            até {formatDateShort(credit.expires_at)}
          </span>
        )}
      </div>
      <QuotaProgress className="mt-2" remaining={credit.remaining_cotas} total={credit.total_cotas} />

      {/* Histórico de consumo — sem endpoint dedicado no contrato atual (gap #3).
          O painel expande de forma lazy; conteúdo real depende de backend. */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="mt-3 flex w-full items-center justify-between rounded-lg border border-border px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        Histórico de consumo
        <ChevronDown
          size={16}
          strokeWidth={1.5}
          className={cn("transition-transform", open && "rotate-180")}
        />
      </button>
      {open && (
        <div className="mt-2 rounded-lg bg-muted/40 px-3 py-3">
          {loadingConsumptions || consumptions === null ? (
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          ) : consumptions.length === 0 ? (
            <p className="text-center text-xs text-muted-foreground">Nenhum consumo registrado.</p>
          ) : (
            <ul className="space-y-1 text-xs text-muted-foreground">
              {consumptions.map((c, i) => (
                <li key={i} className="flex justify-between gap-2">
                  <span className="truncate">
                    {c.service_name ?? "Serviço"}
                    {c.professional_name ? ` · ${c.professional_name}` : ""}
                  </span>
                  <span className="whitespace-nowrap">{formatDateTime(c.occurred_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

export default function PortalCotasPage() {
  const { selectedCompanyId } = useCompanyFilter()
  const [state, setState] = useState<Load>("loading")
  const [credits, setCredits] = useState<PortalCreditItem[]>([])

  const filtered = selectedCompanyId != null

  const load = useCallback(() => {
    setState("loading")
    const q = selectedCompanyId ? `?company_id=${selectedCompanyId}` : ""
    portal
      .get<PortalCreditItem[]>(`/portal/credits${q}`)
      .then((d) => {
        setCredits(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }, [selectedCompanyId])

  useEffect(() => {
    load()
  }, [load])

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Cotas</h1>

      {state === "loading" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full rounded-xl" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" &&
        (credits.length === 0 ? (
          filtered ? (
            <EmptyState title="Nenhuma cota nesta empresa" />
          ) : (
            <EmptyState
              title="Você não tem cotas"
              description="Pacotes e cotas ativas aparecerão aqui."
            />
          )
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {credits.map((c) => (
              <CreditCard key={c.credit_id} credit={c} showCompany={!filtered} />
            ))}
          </div>
        ))}
    </div>
  )
}
