"use client"

import { PortalPageHeader } from "@/components/portal/PortalPageHeader"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { portal } from "@/lib/portal-api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import { type PortalHistoryResponse, establishmentLabel } from "@/lib/portal-types"
import { APPOINTMENT_STATUS_LABELS } from "@/lib/constants"
import { useCompanyFilter } from "@/context/CompanyFilterContext"
import { AppointmentStatusBadge } from "@/components/portal/PortalStatusBadge"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const TZ = "America/Sao_Paulo"
const PAGE_SIZE = 20
const ALL = "ALL"

// O histórico só contém estes status (service.get_history → HISTORY_STATUSES).
// B4 — o backend agora aceita `status` por query → filtro é server-side.
const HISTORY_STATUSES = ["COMPLETED", "CANCELLED", "NO_SHOW"]

type Load = "loading" | "ok" | "error"

export default function PortalHistoricoPage() {
  const router = useRouter()
  // F4a — o Select de empresa próprio foi substituído pelo CompanyFilterBar
  // (Context global); não há mais dois seletores.
  const { selectedCompanyId } = useCompanyFilter()
  const [state, setState] = useState<Load>("loading")
  const [data, setData] = useState<PortalHistoryResponse | null>(null)
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState<string>(ALL)

  const filtered = selectedCompanyId != null

  // Trocar de empresa reseta a paginação ANTES do fetch (ajuste em render —
  // evita buscar uma página que não existe no conjunto filtrado).
  const prevCompany = useRef(selectedCompanyId)
  if (prevCompany.current !== selectedCompanyId) {
    prevCompany.current = selectedCompanyId
    if (page !== 1) setPage(1)
  }

  const load = useCallback(() => {
    setState("loading")
    const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
    if (selectedCompanyId) params.set("company_id", selectedCompanyId)
    if (statusFilter !== ALL) params.set("status", statusFilter) // B4 — filtro server-side
    portal
      .get<PortalHistoryResponse>(`/portal/history?${params.toString()}`)
      .then((d) => {
        setData(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }, [page, selectedCompanyId, statusFilter])

  useEffect(() => {
    load()
  }, [load])

  // B4 — filtro de status agora é server-side (query param); sem filtro client-side.
  const rows = data?.items ?? []

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  return (
    <div className="space-y-6">
      <PortalPageHeader title="Histórico" />

      <div className="flex flex-wrap gap-3">
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            if (!v) return
            setPage(1)
            setStatusFilter(v)
          }}
        >
          <SelectTrigger className="w-52">
            <SelectValue>
              {statusFilter === ALL ? "Todos os status" : APPOINTMENT_STATUS_LABELS[statusFilter]}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Todos os status</SelectItem>
            {HISTORY_STATUSES.map((s) => (
              <SelectItem key={s} value={s}>
                {APPOINTMENT_STATUS_LABELS[s]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

      </div>

      {state === "loading" && (
        <div className="space-y-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" &&
        (rows.length === 0 ? (
          <EmptyState
            title="Nenhum registro"
            description={
              filtered
                ? "Nenhum atendimento nesta empresa para os filtros selecionados."
                : "Não há atendimentos no histórico para os filtros selecionados."
            }
          />
        ) : (
          <>
            {/* Tabela (md+) */}
            <div className="hidden overflow-hidden rounded-xl ring-1 ring-foreground/10 md:block">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <th className="px-4 py-3 font-medium">Serviço</th>
                    <th className="px-4 py-3 font-medium">Profissional</th>
                    {!filtered && <th className="px-4 py-3 font-medium">Estabelecimento</th>}
                    <th className="px-4 py-3 font-medium">Data</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Valor</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((a) => (
                    // F2 — linha leva ao detalhe (status final, sem ações)
                    <tr
                      key={a.id}
                      className="cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-muted/40"
                      onClick={() => router.push(`/portal/agendamento/${a.id}`)}
                    >
                      <td className="px-4 py-3 text-foreground">
                        {a.service_names.join(" + ") || "—"}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {a.professional_name ?? "—"}
                      </td>
                      {!filtered && (
                        <td className="px-4 py-3 text-primary">{establishmentLabel(a)}</td>
                      )}
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDateTime(a.start_at, TZ)}
                      </td>
                      <td className="px-4 py-3">
                        <AppointmentStatusBadge status={a.status} />
                      </td>
                      <td className="px-4 py-3 text-right text-foreground">
                        {formatBRLFromDecimal(a.total_amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Cards (mobile) */}
            <div className="space-y-2 md:hidden">
              {rows.map((a) => (
                // F2 — card leva ao detalhe
                <Link
                  key={a.id}
                  href={`/portal/agendamento/${a.id}`}
                  className="block rounded-xl bg-card p-4 ring-1 ring-foreground/10 transition-colors hover:bg-card/80 hover:ring-primary/30"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium text-foreground">
                      {a.service_names.join(" + ") || "—"}
                    </p>
                    <AppointmentStatusBadge status={a.status} />
                  </div>
                  {!filtered && (
                    <p className="mt-1 text-xs text-primary">{establishmentLabel(a)}</p>
                  )}
                  <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
                    <span>
                      {a.professional_name ? `${a.professional_name} · ` : ""}
                      {formatDateTime(a.start_at, TZ)}
                    </span>
                    <span className="text-foreground">{formatBRLFromDecimal(a.total_amount)}</span>
                  </div>
                </Link>
              ))}
            </div>

            {/* Paginação */}
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
