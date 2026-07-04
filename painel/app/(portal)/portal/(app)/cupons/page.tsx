"use client"

import { useEffect, useState } from "react"
import { Copy, Check, Tag } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatBRLFromDecimal, formatDateShort } from "@/lib/utils"
import { type PortalCouponItem, establishmentLabel } from "@/lib/portal-types"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"

// discount_type pode vir null do backend (Promotion pai removida) — o ramo
// default cobre esse caso além de tipos futuros.
function discountLabel(c: PortalCouponItem): string {
  switch (c.discount_type) {
    case "PERCENTAGE":
      return c.discount_value != null
        ? `${parseFloat(c.discount_value)}% de desconto`
        : "Desconto"
    case "FIXED_AMOUNT":
      return c.discount_value != null
        ? `${formatBRLFromDecimal(c.discount_value)} de desconto`
        : "Desconto"
    default:
      return "Desconto"
  }
}

function CouponCard({ coupon }: { coupon: PortalCouponItem }) {
  const [copied, setCopied] = useState(false)

  function copy() {
    navigator.clipboard?.writeText(coupon.code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="font-display text-xl tracking-[0.2em] text-primary uppercase">
            {coupon.code}
          </p>
          <p className="mt-1 text-sm text-foreground">{discountLabel(coupon)}</p>
        </div>
        {coupon.is_personal && <Badge variant="secondary">Pessoal</Badge>}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>
          {coupon.valid_until ? `Válido até ${formatDateShort(coupon.valid_until)}` : "Sem validade"}
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-md border border-border px-3 py-1.5 transition-colors hover:border-primary/40 hover:text-foreground"
        >
          {copied ? (
            <>
              <Check size={12} strokeWidth={1.5} className="text-primary" /> Copiado!
            </>
          ) : (
            <>
              <Copy size={12} strokeWidth={1.5} /> Copiar
            </>
          )}
        </button>
      </div>

      <p className="mt-3 truncate border-t border-border/60 pt-2 text-[11px] uppercase tracking-widest text-primary/80">
        {establishmentLabel(coupon)}
      </p>
    </div>
  )
}

export default function PortalCuponsPage() {
  const [state, setState] = useState<Load>("loading")
  // Lista plana em estado próprio — filtro por empresa (F4) aplicará sobre ela.
  const [coupons, setCoupons] = useState<PortalCouponItem[]>([])

  function load() {
    setState("loading")
    portal
      .get<PortalCouponItem[]>("/portal/coupons")
      .then((d) => {
        setCoupons(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Cupons</h1>

      {state === "loading" && (
        <div className="grid gap-3 sm:grid-cols-2">
          {Array.from({ length: 2 }).map((_, i) => (
            <Skeleton key={i} className="h-36 w-full rounded-xl" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" &&
        (coupons.length === 0 ? (
          <EmptyState
            icon={<Tag size={28} strokeWidth={1.5} />}
            title="Nenhum cupom"
            description="Você ainda não tem cupons disponíveis."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {coupons.map((c) => (
              <CouponCard key={c.coupon_id} coupon={c} />
            ))}
          </div>
        ))}
    </div>
  )
}
