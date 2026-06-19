"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { ChevronRight } from "lucide-react"
import { owner } from "@/lib/owner-api"
import { formatDateShort, formatDateTime } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { TenantStatusBadge } from "@/components/owner/TenantStatusBadge"
import { TenantStatusDialog } from "@/components/owner/TenantStatusDialog"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  active: boolean
  created_at: string
}

interface TenantHealth {
  company_id: string
  status: string
  total_users: number
  total_customers: number
  appointments_30d: number
  last_activity_at: string | null
  communication_failures_7d: number
  asaas_connected: boolean
  whatsapp_connected: boolean
}

function Kpi({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <Card size="sm">
      <CardContent className="space-y-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="font-display text-2xl tracking-wide text-foreground">{value}</p>
      </CardContent>
    </Card>
  )
}

function ConnectionBadge({ connected }: { connected: boolean }) {
  return (
    <Badge variant={connected ? "default" : "outline"}>
      {connected ? "Conectado" : "Não conectado"}
    </Badge>
  )
}

export default function OwnerTenantDetailPage() {
  const { id } = useParams<{ id: string }>()

  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [tenantLoading, setTenantLoading] = useState(true)
  const [tenantError, setTenantError] = useState<string | null>(null)

  const [health, setHealth] = useState<TenantHealth | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState<string | null>(null)

  const [dialog, setDialog] = useState<"suspend" | "reactivate" | null>(null)

  const loadTenant = useCallback(async () => {
    setTenantLoading(true); setTenantError(null)
    try {
      setTenant(await owner.get<Tenant>(`/platform/tenants/${id}`))
    } catch (err: unknown) {
      setTenantError((err as Error).message)
    } finally {
      setTenantLoading(false)
    }
  }, [id])

  const loadHealth = useCallback(async () => {
    setHealthLoading(true); setHealthError(null)
    try {
      setHealth(await owner.get<TenantHealth>(`/platform/tenants/${id}/health`))
    } catch (err: unknown) {
      setHealthError((err as Error).message)
    } finally {
      setHealthLoading(false)
    }
  }, [id])

  useEffect(() => { loadTenant() }, [loadTenant])
  useEffect(() => { loadHealth() }, [loadHealth])

  function reloadAll() { loadTenant(); loadHealth() }

  const canSuspend = tenant?.status === "ACTIVE" || tenant?.status === "TRIAL"
  const canReactivate = tenant?.status === "SUSPENDED"

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma · Tenant"
        title={tenant?.name ?? "Tenant"}
        description={tenant ? `/${tenant.slug}` : undefined}
      >
        {tenant && <TenantStatusBadge status={tenant.status} />}
        {canSuspend && (
          <Button size="sm" variant="outline" onClick={() => setDialog("suspend")}>Suspender</Button>
        )}
        {canReactivate && (
          <Button size="sm" variant="outline" onClick={() => setDialog("reactivate")}>Reativar</Button>
        )}
      </PageHeader>

      {/* Dados básicos */}
      <section className="space-y-3">
        <h2 className="font-display text-xl tracking-wide text-foreground">Dados</h2>
        {tenantLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : tenantError ? (
          <ErrorState message={tenantError} onRetry={loadTenant} />
        ) : tenant ? (
          <Card>
            <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Nome" value={tenant.name} />
              <Field label="Slug" value={<span className="font-mono text-xs">{tenant.slug}</span>} />
              <Field label="Status" value={<TenantStatusBadge status={tenant.status} />} />
              <Field label="Ativo" value={tenant.active ? "Sim" : "Não"} />
              <Field label="Criado em" value={formatDateShort(tenant.created_at)} />
            </CardContent>
          </Card>
        ) : null}
      </section>

      {/* Saúde */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-display text-xl tracking-wide text-foreground">Saúde</h2>
          <Link
            href={`/owner/tenants/${id}/flags`}
            className="flex items-center gap-1 text-sm text-primary hover:underline"
          >
            Feature flags <ChevronRight size={14} strokeWidth={1.5} />
          </Link>
        </div>
        {healthLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : healthError ? (
          <ErrorState message={healthError} onRetry={loadHealth} />
        ) : health ? (
          <div className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Kpi label="Usuários" value={health.total_users} />
              <Kpi label="Clientes" value={health.total_customers} />
              <Kpi label="Agendamentos (30d)" value={health.appointments_30d} />
              <Kpi
                label="Último acesso"
                value={
                  <span className="text-base">
                    {health.last_activity_at ? formatDateTime(health.last_activity_at) : "—"}
                  </span>
                }
              />
              <Kpi label="Falhas de comunicação (7d)" value={health.communication_failures_7d} />
            </div>
            <Card>
              <CardHeader>
                <CardTitle>Integrações</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-wrap items-center gap-6">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Asaas</span>
                  <ConnectionBadge connected={health.asaas_connected} />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">WhatsApp</span>
                  <ConnectionBadge connected={health.whatsapp_connected} />
                </div>
              </CardContent>
            </Card>
          </div>
        ) : null}
      </section>

      {tenant && dialog && (
        <TenantStatusDialog
          open={!!dialog}
          onOpenChange={(v) => { if (!v) setDialog(null) }}
          companyId={tenant.id}
          tenantName={tenant.name}
          action={dialog}
          onDone={reloadAll}
        />
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div className="text-sm text-foreground">{value}</div>
    </div>
  )
}
