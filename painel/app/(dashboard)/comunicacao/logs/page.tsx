"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Eye, ChevronLeft, ChevronRight } from "lucide-react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import {
  COMMUNICATION_EVENT_TYPE_LABELS,
  COMMUNICATION_EVENT_TYPE_OPTIONS,
  COMMUNICATION_CHANNEL_LABELS,
  COMMUNICATION_AUDIENCE_LABELS,
  COMMUNICATION_LOG_STATUS_LABELS,
} from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CommunicationLogBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"

interface CommunicationLog {
  log_id: string
  company_id: string
  template_id?: string | null
  event_type: string
  channel: string
  recipient_id: string
  recipient_type: string
  status: string
  scheduled_send_at?: string | null
  rendered_body?: string | null
  sent_at?: string | null
  error_message?: string | null
  created_at: string
}

const LIMIT = 50

const STATUS_FILTER: Record<string, string> = {
  all: "Todos",
  SENT: "Enviada", SCHEDULED: "Agendada", FAILED: "Falhou",
  SKIPPED_QUIET_HOURS: "Adiada (silêncio)", SKIPPED_NO_CONSENT: "Sem consentimento",
  SKIPPED_CHANNEL_DISABLED: "Canal desativado", SKIPPED_NO_TEMPLATE: "Sem template",
}
const CHANNEL_FILTER: Record<string, string> = {
  all: "Todos", WHATSAPP: "WhatsApp", EMAIL: "E-mail", SMS: "SMS",
}

function shortId(id: string): string {
  return id.length > 8 ? id.slice(0, 8) : id
}

export default function CommunicationLogsPage() {
  const [logs, setLogs] = useState<CommunicationLog[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(1)

  const [eventFilter, setEventFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [channelFilter, setChannelFilter] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [detail, setDetail] = useState<CommunicationLog | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (eventFilter !== "all") params.set("event_type", eventFilter)
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (channelFilter !== "all") params.set("channel", channelFilter)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    params.set("page", String(page))
    params.set("limit", String(LIMIT))
    try {
      // Paginação ESPECIAL: array plano (sem envelope {total,...})
      setLogs(await api.get<CommunicationLog[]>(`/communication/logs?${params.toString()}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [eventFilter, statusFilter, channelFilter, dateFrom, dateTo, page])

  useEffect(() => { load() }, [load])

  // Reseta página ao mudar qualquer filtro (server-side)
  function setFilter(setter: (v: string) => void, v: string) {
    setter(v); setPage(1)
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Comunicação" title="Logs" description="Histórico de mensagens enviadas, agendadas, falhas e ignoradas.">
        <Button variant="outline" render={<Link href="/comunicacao" />}>Templates</Button>
      </PageHeader>

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1">
          <Label>Evento</Label>
          <Select value={eventFilter} onValueChange={(v) => v && setFilter(setEventFilter, v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{eventFilter === "all" ? "Todos" : COMMUNICATION_EVENT_TYPE_LABELS[eventFilter]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {COMMUNICATION_EVENT_TYPE_OPTIONS.map((e) => (
                <SelectItem key={e} value={e}>{COMMUNICATION_EVENT_TYPE_LABELS[e]}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setFilter(setStatusFilter, v)}>
            <SelectTrigger className="w-full"><SelectValue>{STATUS_FILTER[statusFilter]}</SelectValue></SelectTrigger>
            <SelectContent>
              {Object.entries(STATUS_FILTER).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Canal</Label>
          <Select value={channelFilter} onValueChange={(v) => v && setFilter(setChannelFilter, v)}>
            <SelectTrigger className="w-full"><SelectValue>{CHANNEL_FILTER[channelFilter]}</SelectValue></SelectTrigger>
            <SelectContent>
              {Object.entries(CHANNEL_FILTER).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="log-from">De</Label>
          <Input id="log-from" type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="log-to">Até</Label>
          <Input id="log-to" type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : logs.length === 0 ? (
        <EmptyState title="Nenhum log" description={page > 1 ? "Não há mais registros nesta página." : "Ajuste os filtros ou aguarde novos envios."} />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Evento</th>
                <th className="px-4 py-3 text-left font-medium">Canal</th>
                <th className="px-4 py-3 text-left font-medium">Destinatário</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {logs.map((l) => (
                <tr key={l.log_id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(l.created_at)}</td>
                  <td className="px-4 py-3 font-medium">{COMMUNICATION_EVENT_TYPE_LABELS[l.event_type] ?? l.event_type}</td>
                  <td className="px-4 py-3 text-muted-foreground">{COMMUNICATION_CHANNEL_LABELS[l.channel] ?? l.channel}</td>
                  <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                    {(COMMUNICATION_AUDIENCE_LABELS[l.recipient_type] ?? l.recipient_type)}-{shortId(l.recipient_id)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col gap-0.5">
                      <CommunicationLogBadge status={l.status} />
                      {l.status === "SCHEDULED" && l.scheduled_send_at && (
                        <span className="text-[11px] text-muted-foreground">p/ {formatDateTime(l.scheduled_send_at)}</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <Button size="icon-sm" variant="ghost" aria-label="Ver detalhe" onClick={() => setDetail(l)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Paginação array plano */}
      {!loading && !error && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Página {page}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
              <ChevronLeft className="h-4 w-4" /> Anterior
            </Button>
            <Button variant="outline" size="sm" disabled={logs.length < LIMIT} onClick={() => setPage((p) => p + 1)}>
              Próxima <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Detalhe */}
      <Sheet open={!!detail} onOpenChange={(v) => { if (!v) setDetail(null) }}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Detalhe do envio</SheetTitle>
            <SheetDescription>
              {detail ? (COMMUNICATION_EVENT_TYPE_LABELS[detail.event_type] ?? detail.event_type) : ""}
            </SheetDescription>
          </SheetHeader>
          {detail && (
            <div className="space-y-4 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Status</p>
                  <CommunicationLogBadge status={detail.status} />
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Canal</p>
                  <p>{COMMUNICATION_CHANNEL_LABELS[detail.channel] ?? detail.channel}</p>
                </div>
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Criado</p>
                  <p>{formatDateTime(detail.created_at)}</p>
                </div>
                {detail.sent_at && (
                  <div className="space-y-1">
                    <p className="text-xs text-muted-foreground">Enviado</p>
                    <p>{formatDateTime(detail.sent_at)}</p>
                  </div>
                )}
              </div>

              <div className="space-y-1">
                <p className="text-xs text-muted-foreground">Corpo renderizado</p>
                <div className="rounded-lg border border-border bg-muted/40 p-3 whitespace-pre-wrap">
                  {detail.rendered_body || <span className="text-muted-foreground italic">Indisponível.</span>}
                </div>
              </div>

              {detail.status === "FAILED" && detail.error_message && (
                <div className="space-y-1">
                  <p className="text-xs text-muted-foreground">Erro</p>
                  <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-destructive">
                    {detail.error_message}
                  </p>
                </div>
              )}
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  )
}
