"use client"

import { useCallback, useEffect, useState } from "react"
import { Eye, ChevronLeft, ChevronRight } from "lucide-react"
import { owner } from "@/lib/owner-api"
import { ROLE_LABELS } from "@/lib/constants"
import { formatDateTime } from "@/lib/utils"
import { cn } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

interface AuditLog {
  audit_id: string
  company_id: string | null
  actor_id: string
  actor_role: string
  action: string
  resource_type: string
  resource_id: string | null
  reason: string | null
  before_snapshot: unknown
  after_snapshot: unknown
  occurred_at: string
}

interface Envelope {
  total: number
  page: number
  limit: number
  items: AuditLog[]
}

const LIMIT = 50
const IMPERSONATION_ACTION = "impersonated_request"

// Lista curada das ações conhecidas da plataforma (filtro do screenshot)
const ACTION_OPTIONS = [
  "ALL",
  "tenant.suspended",
  "tenant.reactivated",
  "flag.updated",
  "settings.updated",
  "communication.redispatched",
  IMPERSONATION_ACTION,
]

function shortId(id?: string | null): string {
  if (!id) return "—"
  return id.length > 8 ? id.slice(0, 8) : id
}

export default function OwnerAuditPage() {
  const [tab, setTab] = useState<"all" | "impersonation">("all")

  const [companyId, setCompanyId] = useState("")
  const [actorId, setActorId] = useState("")
  const [action, setAction] = useState("ALL")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [page, setPage] = useState(1)

  const [data, setData] = useState<Envelope | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [detail, setDetail] = useState<AuditLog | null>(null)

  // Ação efetiva: aba Impersonation força o preset; aba Tudo usa o Select
  const effectiveAction = tab === "impersonation"
    ? IMPERSONATION_ACTION
    : (action === "ALL" ? "" : action)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const p = new URLSearchParams()
    if (companyId.trim()) p.set("company_id", companyId.trim())
    if (actorId.trim()) p.set("actor_id", actorId.trim())
    if (effectiveAction) p.set("action", effectiveAction)
    if (dateFrom) p.set("date_from", dateFrom)
    if (dateTo) p.set("date_to", dateTo)
    p.set("page", String(page)); p.set("limit", String(LIMIT))
    try {
      setData(await owner.get<Envelope>(`/platform/audit?${p.toString()}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [companyId, actorId, effectiveAction, dateFrom, dateTo, page])

  useEffect(() => { load() }, [load])

  // Reset de página ao mudar filtros ou aba
  function onFilter<T>(setter: (v: T) => void) {
    return (v: T) => { setter(v); setPage(1) }
  }
  function switchTab(next: "all" | "impersonation") {
    setTab(next); setPage(1)
  }

  const pages = data ? Math.max(1, Math.ceil(data.total / data.limit)) : 1

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Auditoria"
        description="Registros append-only de todas as ações sensíveis da plataforma."
      />

      {/* Abas (segmentadas, controladas) */}
      <div className="inline-flex rounded-lg border border-border p-0.5">
        {([["all", "Tudo"], ["impersonation", "Impersonation"]] as const).map(([val, label]) => (
          <button
            key={val}
            type="button"
            onClick={() => switchTab(val)}
            className={cn(
              "rounded-md px-4 py-1.5 text-sm font-medium transition-colors",
              tab === val ? "bg-secondary text-secondary-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1">
          <Label htmlFor="au-company">company_id</Label>
          <Input id="au-company" value={companyId} onChange={(e) => onFilter(setCompanyId)(e.target.value)} placeholder="t-001" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-actor">actor_id</Label>
          <Input id="au-actor" value={actorId} onChange={(e) => onFilter(setActorId)(e.target.value)} placeholder="user-1" />
        </div>
        <div className="space-y-1">
          <Label>action</Label>
          <Select value={action} onValueChange={(v) => v && onFilter(setAction)(v)} disabled={tab === "impersonation"}>
            <SelectTrigger className="w-full">
              <SelectValue>{action === "ALL" ? "Todas" : action}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {ACTION_OPTIONS.map((a) => (
                <SelectItem key={a} value={a}>{a === "ALL" ? "Todas" : a}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-from">De</Label>
          <Input id="au-from" type="date" value={dateFrom} onChange={(e) => onFilter(setDateFrom)(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-to">Até</Label>
          <Input id="au-to" type="date" value={dateTo} onChange={(e) => onFilter(setDateTo)(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-96 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : !data || data.items.length === 0 ? (
        <EmptyState title="Nenhum registro" description="Ajuste os filtros." />
      ) : (
        <>
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>company_id</TableHead>
                  <TableHead>Ator</TableHead>
                  <TableHead>Ação</TableHead>
                  <TableHead>Recurso</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Ocorrido em</TableHead>
                  <TableHead className="text-right">Snap.</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((l) => (
                  <TableRow key={l.audit_id}>
                    <TableCell className="font-mono text-xs">{l.company_id ?? "—"}</TableCell>
                    <TableCell>
                      <span className="flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">{shortId(l.actor_id)}</span>
                        <Badge variant="outline">{ROLE_LABELS[l.actor_role] ?? l.actor_role}</Badge>
                      </span>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{l.action}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {l.resource_type}{l.resource_id ? ` ${shortId(l.resource_id)}` : ""}
                    </TableCell>
                    <TableCell className="max-w-xs whitespace-normal text-muted-foreground">{l.reason || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(l.occurred_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button size="icon-sm" variant="ghost" aria-label="Ver snapshots" onClick={() => setDetail(l)}>
                        <Eye className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">Página {data.page} de {pages}</p>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                <ChevronLeft className="h-4 w-4" /> Anterior
              </Button>
              <Button variant="outline" size="sm" disabled={data.page >= pages} onClick={() => setPage((p) => Math.min(pages, p + 1))}>
                Próxima <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Detalhe — snapshots (read-only) */}
      <Dialog open={!!detail} onOpenChange={(v) => { if (!v) setDetail(null) }}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-mono">{detail?.action}</DialogTitle>
            <DialogDescription>
              {detail ? `${detail.resource_type}${detail.resource_id ? ` · ${detail.resource_id}` : ""} · ${formatDateTime(detail.occurred_at)}` : ""}
            </DialogDescription>
          </DialogHeader>
          {detail && (
            <div className="space-y-4">
              <JsonBlock title="before_snapshot" value={detail.before_snapshot} />
              <JsonBlock title="after_snapshot" value={detail.after_snapshot} />
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="space-y-1">
      <p className="font-mono text-xs text-muted-foreground">{title}</p>
      <pre className="max-h-60 overflow-auto rounded-lg border border-border bg-muted/40 p-3 text-xs">
        {value != null ? JSON.stringify(value, null, 2) : "—"}
      </pre>
    </div>
  )
}
