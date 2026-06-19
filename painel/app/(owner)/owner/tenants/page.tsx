"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { owner } from "@/lib/owner-api"
import { formatDateShort } from "@/lib/utils"
import { TENANT_STATUS_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { TenantStatusBadge } from "@/components/owner/TenantStatusBadge"
import { TenantStatusDialog } from "@/components/owner/TenantStatusDialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  active: boolean
  created_at: string
}

interface TenantList {
  items: Tenant[]
  total: number
}

const STATUS_OPTIONS = ["ALL", "TRIAL", "ACTIVE", "SUSPENDED", "CHURNED"] as const

export default function OwnerTenantsPage() {
  const router = useRouter()

  const [status, setStatus] = useState<string>("ALL")
  const [search, setSearch] = useState("")
  const [data, setData] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Dialog de status
  const [dialog, setDialog] = useState<{ tenant: Tenant; action: "suspend" | "reactivate" } | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const p = new URLSearchParams()
    if (status !== "ALL") p.set("status", status)
    try {
      const res = await owner.get<TenantList>(`/platform/tenants${p.toString() ? `?${p.toString()}` : ""}`)
      setData(res.items)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [status])

  useEffect(() => { load() }, [load])

  // Busca client-side por nome OU slug (substring case-insensitive)
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return data
    return data.filter(
      (t) => t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q),
    )
  }, [data, search])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Tenants"
        description="Visão de todos os estabelecimentos da plataforma."
      />

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={status} onValueChange={(v) => v && setStatus(v)}>
          <SelectTrigger className="w-48">
            <SelectValue>
              {status === "ALL" ? "Todos os status" : TENANT_STATUS_LABELS[status] ?? status}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "ALL" ? "Todos os status" : TENANT_STATUS_LABELS[s] ?? s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Input
          className="w-72"
          placeholder="Buscar por nome ou slug…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {loading ? (
        <Skeleton className="h-80 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState
          title="Nenhum tenant"
          description={search || status !== "ALL" ? "Ajuste os filtros." : "Nenhum estabelecimento cadastrado."}
        />
      ) : (
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Slug</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Criado em</TableHead>
                <TableHead>Ativo</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((t) => {
                const canSuspend = t.status === "ACTIVE" || t.status === "TRIAL"
                const canReactivate = t.status === "SUSPENDED"
                return (
                  <TableRow
                    key={t.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/owner/tenants/${t.id}`)}
                  >
                    <TableCell className="font-medium">{t.name}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{t.slug}</TableCell>
                    <TableCell><TenantStatusBadge status={t.status} /></TableCell>
                    <TableCell className="text-muted-foreground">{formatDateShort(t.created_at)}</TableCell>
                    <TableCell className="text-muted-foreground">{t.active ? "Sim" : "Não"}</TableCell>
                    <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                      {canSuspend ? (
                        <Button size="sm" variant="outline" onClick={() => setDialog({ tenant: t, action: "suspend" })}>
                          Suspender
                        </Button>
                      ) : canReactivate ? (
                        <Button size="sm" variant="outline" onClick={() => setDialog({ tenant: t, action: "reactivate" })}>
                          Reativar
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {dialog && (
        <TenantStatusDialog
          open={!!dialog}
          onOpenChange={(v) => { if (!v) setDialog(null) }}
          companyId={dialog.tenant.id}
          tenantName={dialog.tenant.name}
          action={dialog.action}
          onDone={load}
        />
      )}
    </div>
  )
}
