"use client"

import { useEffect, useState } from "react"
import { ChevronDown } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatDateShort } from "@/lib/utils"
import { type PortalCreditItem, establishmentLabel } from "@/lib/portal-types"
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

function CreditCard({ credit }: { credit: PortalCreditItem }) {
  const [open, setOpen] = useState(false)
  const expired = isExpired(credit)

  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{credit.entitlement_type}</p>
          <p className="truncate text-xs text-primary">{establishmentLabel(credit)}</p>
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
        <div className="mt-2 rounded-lg bg-muted/40 px-3 py-4 text-center text-xs text-muted-foreground">
          Em breve — o detalhamento de consumo estará disponível aqui.
        </div>
      )}
    </div>
  )
}

export default function PortalCotasPage() {
  const [state, setState] = useState<Load>("loading")
  const [credits, setCredits] = useState<PortalCreditItem[]>([])

  function load() {
    setState("loading")
    portal
      .get<PortalCreditItem[]>("/portal/credits")
      .then((d) => {
        setCredits(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

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
          <EmptyState title="Você não tem cotas" description="Pacotes e cotas ativas aparecerão aqui." />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {credits.map((c) => (
              <CreditCard key={c.credit_id} credit={c} />
            ))}
          </div>
        ))}
    </div>
  )
}
