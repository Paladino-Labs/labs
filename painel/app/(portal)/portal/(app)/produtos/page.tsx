"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { Package } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { cn, formatBRLFromDecimal, formatDateShort } from "@/lib/utils"
import {
  type PortalProductSaleItem,
  type PortalProductSalesResponse,
  establishmentLabel,
} from "@/lib/portal-types"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"

// Chave da visão = valor do query param ?status= ("" = histórico completo).
type ViewKey = "" | "RESERVED" | "PURCHASED"

interface ViewState {
  state: Load
  items: PortalProductSaleItem[]
  total: number
}

const INITIAL_VIEW: ViewState = { state: "loading", items: [], total: 0 }

const TABS: { key: ViewKey; label: string }[] = [
  { key: "",          label: "Histórico" },
  { key: "RESERVED",  label: "Reservados" },
  { key: "PURCHASED", label: "Comprados p/ retirada" },
]

const EMPTY_MSG: Record<ViewKey, string> = {
  "":          "Você ainda não comprou produtos.",
  RESERVED:    "Nenhum produto reservado.",
  PURCHASED:   "Nenhum produto comprado ainda.",
}

const HINT: Record<ViewKey, string | null> = {
  "":          null,
  RESERVED:    "Pague e retire na barbearia.",
  PURCHASED:   "Retire na barbearia.",
}

// Cores seguem o precedente de PortalStatusBadge (emerald/amber hardcoded —
// não há tokens semânticos de sucesso/aviso no design system).
function SaleStatusBadge({ status }: { status: string }) {
  if (status === "RESERVED")
    return (
      <Badge className="border-transparent bg-amber-500/10 text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
        Reservado
      </Badge>
    )
  if (status === "PICKED_UP")
    return (
      <Badge className="border-transparent bg-emerald-500/10 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400">
        Retirado
      </Badge>
    )
  if (status === "PURCHASED") return <Badge>Comprado</Badge>
  return <Badge variant="secondary">{status}</Badge>
}

function SaleCard({ sale, hint }: { sale: PortalProductSaleItem; hint: string | null }) {
  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-foreground">{sale.product_name}</p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {sale.quantity}un · {formatBRLFromDecimal(sale.unit_price)}
          </p>
          <p className="mt-1 truncate text-[11px] uppercase tracking-widest text-primary/80">
            {establishmentLabel(sale)}
          </p>
        </div>
        <div className="flex flex-shrink-0 flex-col items-end gap-1">
          <SaleStatusBadge status={sale.status} />
          <span className="text-[11px] text-muted-foreground">
            {formatDateShort(sale.created_at)}
          </span>
        </div>
      </div>
      {hint && sale.status !== "PICKED_UP" && (
        <p className="mt-3 rounded-md bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  )
}

export default function PortalProdutosPage() {
  const [tab, setTab] = useState<ViewKey>("")
  // Uma entrada por visão — o filtro por empresa (F4) aplicará sobre `items`.
  const [views, setViews] = useState<Record<ViewKey, ViewState>>({
    "": INITIAL_VIEW,
    RESERVED: INITIAL_VIEW,
    PURCHASED: INITIAL_VIEW,
  })

  // Visões já buscadas (evita refetch ao alternar abas; F4 pode invalidar).
  const requested = useRef<Set<ViewKey>>(new Set())

  const load = useCallback((key: ViewKey) => {
    requested.current.add(key)
    setViews((v) => ({ ...v, [key]: { ...v[key], state: "loading" } }))
    const qs = key ? `?status=${key}` : ""
    portal
      .get<PortalProductSalesResponse>(`/portal/product-sales${qs}`)
      .then((d) =>
        setViews((v) => ({ ...v, [key]: { state: "ok", items: d.items, total: d.total } })),
      )
      .catch(() =>
        setViews((v) => ({ ...v, [key]: { ...v[key], state: "error" } })),
      )
  }, [])

  // Histórico (visão inicial) + Reservados (contagem "· N" da aba) no mount.
  useEffect(() => {
    load("")
    load("RESERVED")
  }, [load])

  function switchTab(key: ViewKey) {
    setTab(key)
    if (!requested.current.has(key)) load(key) // PURCHASED é lazy (1º clique)
  }

  const view = views[tab]
  const reservedCount = views.RESERVED.state === "ok" ? views.RESERVED.total : 0
  const hint = HINT[tab]

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Produtos</h1>

      {/* Tabs manuais no idioma do portal — roláveis no mobile */}
      <div className="-mx-4 overflow-x-auto px-4 md:mx-0 md:px-0">
        <div className="inline-flex gap-1 rounded-lg bg-muted/60 p-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => switchTab(t.key)}
              className={cn(
                "whitespace-nowrap rounded-md px-3 py-2 text-sm transition-colors",
                tab === t.key
                  ? "bg-background font-medium text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              {t.label}
              {t.key === "RESERVED" && reservedCount > 0 && ` · ${reservedCount}`}
            </button>
          ))}
        </div>
      </div>

      {view.state === "loading" && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      )}
      {view.state === "error" && <ErrorState onRetry={() => load(tab)} />}
      {view.state === "ok" &&
        (view.items.length === 0 ? (
          <EmptyState
            icon={<Package size={28} strokeWidth={1.5} />}
            title="Nenhum produto"
            description={EMPTY_MSG[tab]}
          />
        ) : (
          <div className="space-y-3">
            {view.items.map((s) => (
              <SaleCard key={s.sale_id} sale={s} hint={hint} />
            ))}
          </div>
        ))}
    </div>
  )
}
