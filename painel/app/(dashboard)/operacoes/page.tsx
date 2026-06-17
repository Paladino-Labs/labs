"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Search, ChevronRight } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { Appointment, Professional } from "@/types"
import { APPOINTMENT_STATUS_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { AppointmentBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const STATUS_OPTIONS = ["SCHEDULED", "REQUESTED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "NO_SHOW"]

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export default function OperacoesPage() {
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [profFilter, setProfFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [from, setFrom] = useState(today())
  const [to, setTo] = useState(today())
  const [clientQuery, setClientQuery] = useState("")

  const profMap = useMemo(() => new Map(professionals.map((p) => [p.id, p.name])), [professionals])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const params = new URLSearchParams({ page_size: "200" })
      if (from) params.set("start_after", new Date(`${from}T00:00:00`).toISOString())
      if (to) params.set("start_before", new Date(`${to}T23:59:59`).toISOString())
      const [appts, profs] = await Promise.all([
        api.get<Appointment[]>(`/appointments/?${params}`),
        api.get<Professional[]>("/professionals/"),
      ])
      setAppointments(appts)
      setProfessionals(profs)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [from, to])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => {
    const q = clientQuery.trim().toLowerCase()
    return appointments
      .filter((a) => profFilter === "all" || a.professional_id === profFilter)
      .filter((a) => statusFilter === "all" || a.status === statusFilter)
      .filter((a) => !q || (a.customer?.name ?? "").toLowerCase().includes(q))
  }, [appointments, profFilter, statusFilter, clientQuery])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Operação" title="Operações" description="Todos os atendimentos do tenant.">
        <Button onClick={() => router.push("/appointments/new")}>+ Novo Agendamento</Button>
      </PageHeader>

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1">
          <Label>Barbeiro</Label>
          <Select value={profFilter} onValueChange={(v) => v && setProfFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{profFilter === "all" ? "Todos" : (profMap.get(profFilter) ?? "—")}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {professionals.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{statusFilter === "all" ? "Todos" : (APPOINTMENT_STATUS_LABELS[statusFilter] ?? statusFilter)}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {STATUS_OPTIONS.map((s) => <SelectItem key={s} value={s}>{APPOINTMENT_STATUS_LABELS[s] ?? s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="op-from">De</Label>
          <Input id="op-from" type="date" value={from} onChange={(e) => setFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="op-to">Até</Label>
          <Input id="op-to" type="date" value={to} onChange={(e) => setTo(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="op-client">Buscar cliente</Label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="op-client" value={clientQuery} onChange={(e) => setClientQuery(e.target.value)}
              placeholder="Nome do cliente" className="pl-9" />
          </div>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-72 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState title="Nenhum atendimento" description="Ajuste os filtros ou crie um novo agendamento." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data/Hora</th>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Serviço</th>
                <th className="px-4 py-3 text-left font-medium">Barbeiro</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((a) => (
                <tr
                  key={a.id}
                  onClick={() => router.push(`/appointments/${a.id}`)}
                  className="cursor-pointer transition-colors hover:bg-muted/30"
                >
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(a.start_at)}</td>
                  <td className="px-4 py-3 font-medium">{a.customer?.name ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{a.services.map((s) => s.service_name).join(", ") || "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{a.professional?.name ?? profMap.get(a.professional_id) ?? "—"}</td>
                  <td className="px-4 py-3"><AppointmentBadge status={a.status} /></td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(a.total_amount)}</td>
                  <td className="px-4 py-3 text-right"><ChevronRight className="ml-auto h-4 w-4 text-muted-foreground" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
