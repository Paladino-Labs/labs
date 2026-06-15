"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { AlertTriangle, UserPlus, Star, Sparkles } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { Customer } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

interface AtRiskCustomer {
  customer_id: string
  days_since_last_visit: number
  computed_at: string
}

interface CrmAlerts {
  at_risk_count: number
  at_risk_customers: AtRiskCustomer[]
  new_this_month: number
  vip_count: number
  recovered_this_week: number
}

export default function CrmPage() {
  const { role } = useAuth()
  const allowed = role === "OWNER" || role === "ADMIN"

  const [alerts, setAlerts] = useState<CrmAlerts | null>(null)
  const [names, setNames] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<CrmAlerts>("/crm/alerts")
      setAlerts(data)
      try {
        const customers = await api.get<Customer[]>("/customers/")
        setNames(new Map(customers.map((c) => [c.id, c.name])))
      } catch {
        /* nomes ficam como ID se /customers falhar */
      }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (allowed) load()
    else setLoading(false)
  }, [allowed, load])

  if (!allowed) {
    return (
      <EmptyState
        title="Sem acesso"
        description="Esta área é restrita a Proprietário e Administrador."
      />
    )
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-48" />
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-24 w-full" />)}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (error || !alerts) {
    return <ErrorState message={error ?? undefined} onRetry={load} />
  }

  const topAtRisk = [...alerts.at_risk_customers]
    .sort((a, b) => b.days_since_last_visit - a.days_since_last_visit)
    .slice(0, 10)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Relacionamento"
        title="CRM"
        description="Visão consolidada de risco, novos clientes e oportunidades."
      />

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Kpi icon={<AlertTriangle size={16} strokeWidth={1.5} />} label="Em risco" value={alerts.at_risk_count} />
        <Kpi icon={<UserPlus size={16} strokeWidth={1.5} />} label="Novos no mês" value={alerts.new_this_month} />
        <Kpi icon={<Star size={16} strokeWidth={1.5} />} label="VIP" value={alerts.vip_count} />
        <Kpi icon={<Sparkles size={16} strokeWidth={1.5} />} label="Recuperados (semana)" value={alerts.recovered_this_week} />
      </div>

      <Card>
        <CardHeader><CardTitle className="font-display text-xl">Top 10 em risco</CardTitle></CardHeader>
        <CardContent className="p-0">
          {topAtRisk.length === 0 ? (
            <EmptyState message="Tudo em dia — nenhum cliente em risco." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead className="text-right">Dias sem visita</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {topAtRisk.map((c) => (
                  <TableRow key={c.customer_id}>
                    <TableCell>{names.get(c.customer_id) ?? c.customer_id}</TableCell>
                    <TableCell className="text-right font-mono">{c.days_since_last_visit}</TableCell>
                    <TableCell>
                      <Button size="sm" variant="outline" render={<Link href={`/customers/${c.customer_id}`} />}>
                        Abrir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="font-display text-xl">Sugestões de ação</CardTitle></CardHeader>
        <CardContent>
          <ul className="space-y-3 text-sm">
            <li className="rounded-md border border-border bg-card px-3 py-2.5">
              <p className="font-medium">Reativar clientes em risco</p>
              <p className="text-xs text-muted-foreground">
                {alerts.at_risk_count} cliente(s) sem visita recente — considere uma campanha de retorno.
              </p>
            </li>
            <li className="rounded-md border border-border bg-card px-3 py-2.5">
              <p className="font-medium">Fidelizar VIPs</p>
              <p className="text-xs text-muted-foreground">
                {alerts.vip_count} cliente(s) VIP — elegíveis para pacotes e benefícios exclusivos.
              </p>
            </li>
            <li className="rounded-md border border-border bg-card px-3 py-2.5">
              <p className="font-medium">Acolher novos clientes</p>
              <p className="text-xs text-muted-foreground">
                {alerts.new_this_month} novo(s) no mês — envie boas-vindas e incentive o retorno.
              </p>
            </li>
          </ul>
        </CardContent>
      </Card>
    </div>
  )
}

function Kpi({ icon, label, value }: { icon: React.ReactNode; label: string; value: number | string }) {
  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
          {icon} {label}
        </div>
        <p className="font-display text-3xl">{value}</p>
      </CardContent>
    </Card>
  )
}
