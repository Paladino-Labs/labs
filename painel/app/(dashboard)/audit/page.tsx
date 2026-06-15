"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Eye, Download, ChevronLeft, ChevronRight } from "lucide-react"
import { api, BASE } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { ROLE_LABELS } from "@/lib/constants"
import { formatDateTime } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"

interface AuditLog {
  audit_id: string
  company_id?: string | null
  actor_id: string
  actor_role: string
  action: string
  resource_type: string
  resource_id?: string | null
  reason?: string | null
  before_snapshot?: unknown
  after_snapshot?: unknown
  occurred_at: string
  ip_address?: string | null
}

interface ImpersonationAccess {
  audit_id: string
  grant_id?: string | null
  actor_id: string
  reason?: string | null
  request: unknown
  occurred_at: string
}

interface Envelope<T> {
  total: number
  page: number
  limit: number
  items: T[]
}

const LIMIT = 50

function shortId(id?: string | null): string {
  if (!id) return "—"
  return id.length > 8 ? id.slice(0, 8) : id
}

export default function AuditPage() {
  const { role } = useAuth()
  const isOwner = role === "OWNER"

  const [action, setAction] = useState("")
  const [actorId, setActorId] = useState("")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [trail, setTrail] = useState<Envelope<AuditLog> | null>(null)
  const [trailPage, setTrailPage] = useState(1)
  const [trailLoading, setTrailLoading] = useState(true)
  const [trailError, setTrailError] = useState<string | null>(null)

  const [imp, setImp] = useState<Envelope<ImpersonationAccess> | null>(null)
  const [impPage, setImpPage] = useState(1)
  const [impLoading, setImpLoading] = useState(true)
  const [impError, setImpError] = useState<string | null>(null)

  const [snapshot, setSnapshot] = useState<AuditLog | null>(null)
  const [request, setRequest] = useState<ImpersonationAccess | null>(null)
  const [exporting, setExporting] = useState(false)

  function filterParams(): URLSearchParams {
    const p = new URLSearchParams()
    if (action.trim()) p.set("action", action.trim())
    if (actorId.trim()) p.set("actor_id", actorId.trim())
    if (dateFrom) p.set("date_from", dateFrom)
    if (dateTo) p.set("date_to", dateTo)
    return p
  }

  const loadTrail = useCallback(async () => {
    setTrailLoading(true); setTrailError(null)
    const p = new URLSearchParams()
    if (action.trim()) p.set("action", action.trim())
    if (actorId.trim()) p.set("actor_id", actorId.trim())
    if (dateFrom) p.set("date_from", dateFrom)
    if (dateTo) p.set("date_to", dateTo)
    p.set("page", String(trailPage)); p.set("limit", String(LIMIT))
    try {
      setTrail(await api.get<Envelope<AuditLog>>(`/audit/logs?${p.toString()}`))
    } catch (err: unknown) {
      setTrailError((err as Error).message)
    } finally {
      setTrailLoading(false)
    }
  }, [action, actorId, dateFrom, dateTo, trailPage])

  const loadImp = useCallback(async () => {
    setImpLoading(true); setImpError(null)
    const p = new URLSearchParams()
    p.set("page", String(impPage)); p.set("limit", String(LIMIT))
    try {
      setImp(await api.get<Envelope<ImpersonationAccess>>(`/audit/impersonation-accesses?${p.toString()}`))
    } catch (err: unknown) {
      setImpError((err as Error).message)
    } finally {
      setImpLoading(false)
    }
  }, [impPage])

  useEffect(() => { loadTrail() }, [loadTrail])
  useEffect(() => { loadImp() }, [loadImp])

  // Reset de página ao alterar filtros (trilha)
  function onFilterChange(setter: (v: string) => void) {
    return (v: string) => { setter(v); setTrailPage(1) }
  }

  async function handleExport() {
    setExporting(true)
    try {
      const token = typeof window !== "undefined" ? localStorage.getItem("token") : null
      const res = await fetch(`${BASE}/audit/logs/export?${filterParams().toString()}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
      if (!res.ok) throw new Error(res.status === 403 ? "Apenas o Proprietário pode exportar." : "Falha ao exportar.")
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = "audit_logs.csv"
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      toast.success("Exportação concluída")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao exportar")
    } finally {
      setExporting(false)
    }
  }

  const trailPages = trail ? Math.max(1, Math.ceil(trail.total / trail.limit)) : 1
  const impPages = imp ? Math.max(1, Math.ceil(imp.total / imp.limit)) : 1

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administração" title="Auditoria" description="Trilha imutável de ações e acessos. Somente leitura.">
        {isOwner ? (
          <Button variant="outline" onClick={handleExport} disabled={exporting}>
            <Download className="h-4 w-4" /> {exporting ? "Exportando…" : "Exportar CSV"}
          </Button>
        ) : (
          <Tooltip>
            <TooltipTrigger render={<span />}>
              <Button variant="outline" disabled>
                <Download className="h-4 w-4" /> Exportar CSV
              </Button>
            </TooltipTrigger>
            <TooltipContent>Apenas o Proprietário pode exportar.</TooltipContent>
          </Tooltip>
        )}
      </PageHeader>

      {/* Filtros (trilha) */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="au-action">Ação contém</Label>
          <Input id="au-action" value={action} onChange={(e) => onFilterChange(setAction)(e.target.value)} placeholder="user.role_changed" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-actor">Ator ID</Label>
          <Input id="au-actor" value={actorId} onChange={(e) => onFilterChange(setActorId)(e.target.value)} placeholder="u-1" />
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-from">De</Label>
          <Input id="au-from" type="date" value={dateFrom} onChange={(e) => onFilterChange(setDateFrom)(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="au-to">Até</Label>
          <Input id="au-to" type="date" value={dateTo} onChange={(e) => onFilterChange(setDateTo)(e.target.value)} />
        </div>
      </div>

      <Tabs defaultValue="trail">
        <TabsList>
          <TabsTrigger value="trail">Trilha</TabsTrigger>
          <TabsTrigger value="impersonation">Acessos de impersonation</TabsTrigger>
        </TabsList>

        {/* Trilha */}
        <TabsContent value="trail" className="space-y-4">
          {trailLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : trailError ? (
            <ErrorState message={trailError} onRetry={loadTrail} />
          ) : !trail || trail.items.length === 0 ? (
            <EmptyState title="Nenhum registro" description="Ajuste os filtros." />
          ) : (
            <>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Data</th>
                      <th className="px-4 py-3 text-left font-medium">Ator</th>
                      <th className="px-4 py-3 text-left font-medium">Ação</th>
                      <th className="px-4 py-3 text-left font-medium">Recurso</th>
                      <th className="px-4 py-3 text-left font-medium">Motivo</th>
                      <th className="px-4 py-3 text-left font-medium">IP</th>
                      <th className="px-4 py-3 text-right font-medium">Snap.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {trail.items.map((l) => (
                      <tr key={l.audit_id} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 text-muted-foreground">{formatDateTime(l.occurred_at)}</td>
                        <td className="px-4 py-3">
                          <span className="flex items-center gap-2">
                            <span className="font-mono text-xs text-muted-foreground">{shortId(l.actor_id)}</span>
                            <Badge variant="outline">{ROLE_LABELS[l.actor_role] ?? l.actor_role}</Badge>
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-xs">{l.action}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">
                          {l.resource_type}{l.resource_id ? `-${shortId(l.resource_id)}` : ""}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">{l.reason || "—"}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{l.ip_address || "—"}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end">
                            <Button size="icon-sm" variant="ghost" aria-label="Ver snapshots" onClick={() => setSnapshot(l)}>
                              <Eye className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={trail.page} pages={trailPages}
                onPrev={() => setTrailPage((p) => Math.max(1, p - 1))}
                onNext={() => setTrailPage((p) => Math.min(trailPages, p + 1))}
              />
            </>
          )}
        </TabsContent>

        {/* Impersonation */}
        <TabsContent value="impersonation" className="space-y-4">
          {impLoading ? (
            <Skeleton className="h-64 w-full" />
          ) : impError ? (
            <ErrorState message={impError} onRetry={loadImp} />
          ) : !imp || imp.items.length === 0 ? (
            <EmptyState title="Nenhum acesso" description="Não há acessos de impersonation registrados." />
          ) : (
            <>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Data</th>
                      <th className="px-4 py-3 text-left font-medium">Grant</th>
                      <th className="px-4 py-3 text-left font-medium">Ator</th>
                      <th className="px-4 py-3 text-left font-medium">Motivo</th>
                      <th className="px-4 py-3 text-right font-medium">Req.</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {imp.items.map((a) => (
                      <tr key={a.audit_id} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 text-muted-foreground">{formatDateTime(a.occurred_at)}</td>
                        <td className="px-4 py-3 font-mono text-xs text-muted-foreground">{shortId(a.grant_id)}</td>
                        <td className="px-4 py-3 font-mono text-xs">{shortId(a.actor_id)}</td>
                        <td className="px-4 py-3 text-muted-foreground">{a.reason || "—"}</td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end">
                            <Button size="icon-sm" variant="ghost" aria-label="Ver requisição" onClick={() => setRequest(a)}>
                              <Eye className="h-4 w-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={imp.page} pages={impPages}
                onPrev={() => setImpPage((p) => Math.max(1, p - 1))}
                onNext={() => setImpPage((p) => Math.min(impPages, p + 1))}
              />
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* Snapshot Sheet */}
      <Sheet open={!!snapshot} onOpenChange={(v) => { if (!v) setSnapshot(null) }}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Snapshots</SheetTitle>
            <SheetDescription>{snapshot?.action}</SheetDescription>
          </SheetHeader>
          {snapshot && (
            <div className="space-y-4 text-sm">
              <JsonBlock title="Antes" value={snapshot.before_snapshot} />
              <JsonBlock title="Depois" value={snapshot.after_snapshot} />
            </div>
          )}
        </SheetContent>
      </Sheet>

      {/* Request Sheet */}
      <Sheet open={!!request} onOpenChange={(v) => { if (!v) setRequest(null) }}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Requisição</SheetTitle>
            <SheetDescription>{request ? formatDateTime(request.occurred_at) : ""}</SheetDescription>
          </SheetHeader>
          {request && <JsonBlock title="Requisição" value={request.request} />}
        </SheetContent>
      </Sheet>
    </div>
  )
}

function Pagination({ page, pages, onPrev, onNext }: { page: number; pages: number; onPrev: () => void; onNext: () => void }) {
  return (
    <div className="flex items-center justify-between">
      <p className="text-sm text-muted-foreground">Página {page} de {pages}</p>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={onPrev}>
          <ChevronLeft className="h-4 w-4" /> Anterior
        </Button>
        <Button variant="outline" size="sm" disabled={page >= pages} onClick={onNext}>
          Próxima <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}

function JsonBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{title}</p>
      <pre className="overflow-x-auto rounded-lg border border-border bg-muted/40 p-3 text-xs">
        {value != null ? JSON.stringify(value, null, 2) : "—"}
      </pre>
    </div>
  )
}
