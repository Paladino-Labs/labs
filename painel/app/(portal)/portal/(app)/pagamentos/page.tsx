"use client"

// Redesign F3 — histórico de pagamentos read-only.
// A gestão de cartões salvos (payment-sources) fica para o sprint de pagamento
// online (tokenização Asaas) — não criar UI de cartões aqui.

import { useCallback, useEffect, useState } from "react"
import { portal } from "@/lib/portal-api"
import { formatBRLFromDecimal, formatDateShort } from "@/lib/utils"
import { type PortalPaymentsResponse, establishmentLabel } from "@/lib/portal-types"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"
import { PaymentStatusBadge } from "@/components/portal/PortalStatusBadge"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"

const PAGE_SIZE = 20

type Load = "loading" | "ok" | "error"

export default function PortalPagamentosPage() {
  const [state, setState] = useState<Load>("loading")
  const [data, setData] = useState<PortalPaymentsResponse | null>(null)
  const [page, setPage] = useState(1)

  const load = useCallback(() => {
    setState("loading")
    portal
      .get<PortalPaymentsResponse>(`/portal/payments?page=${page}&page_size=${PAGE_SIZE}`)
      .then((d) => {
        setData(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }, [page])

  useEffect(() => {
    load()
  }, [load])

  const rows = data?.items ?? []
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Pagamentos</h1>

      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" &&
        (rows.length === 0 ? (
          <EmptyState
            title="Nenhum pagamento"
            description="Você ainda não tem pagamentos registrados."
          />
        ) : (
          <>
            <ul className="space-y-2">
              {rows.map((p) => (
                <li
                  key={p.payment_id}
                  className="rounded-xl bg-card p-4 ring-1 ring-foreground/10"
                >
                  <div className="flex items-start justify-between gap-3">
                    {/* Sem descrição semântica no backend — a linha principal é o
                        estabelecimento; método + data na secundária. */}
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {establishmentLabel(p)}
                      </p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method}
                        {" · "}
                        {formatDateShort(p.paid_at ?? p.created_at)}
                      </p>
                      {p.coupon_code && (
                        <p className="mt-1 inline-block rounded-full bg-primary/10 px-2 py-0.5 text-[11px] tracking-widest text-primary">
                          Cupom {p.coupon_code}
                        </p>
                      )}
                    </div>
                    <div className="flex flex-shrink-0 flex-col items-end gap-1">
                      <p className="whitespace-nowrap text-sm font-medium text-foreground">
                        {formatBRLFromDecimal(p.amount)}
                      </p>
                      <PaymentStatusBadge status={p.status} />
                    </div>
                  </div>
                </li>
              ))}
            </ul>

            {/* Paginação — mesmo padrão do histórico */}
            <div className="flex items-center justify-between">
              <p className="text-xs text-muted-foreground">
                Página {data!.page} de {totalPages} · {data!.total} registros
              </p>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Anterior
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Próxima
                </Button>
              </div>
            </div>
          </>
        ))}
    </div>
  )
}
