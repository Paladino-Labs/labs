"use client"

import { useEffect, useState, useMemo } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import { formatDateTime, formatBRL } from "@/lib/utils"
import { APPOINTMENT_STATUS_LABELS, APPOINTMENT_STATUS_VARIANT } from "@/lib/constants"
import type { Appointment, Professional } from "@/types"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// ── Filtros de data ──────────────────────────────────────────────────────────
type DateFilter = "hoje" | "semana" | "mes" | "todos"

function startOfWeek(): Date {
  const d = new Date()
  d.setDate(d.getDate() - d.getDay())
  d.setHours(0, 0, 0, 0)
  return d
}

function matchesDate(isoStr: string, filter: DateFilter): boolean {
  if (filter === "todos") return true
  const d = new Date(isoStr)
  const today = new Date()
  if (filter === "hoje") {
    return d.toDateString() === today.toDateString()
  }
  if (filter === "semana") {
    const sw = startOfWeek()
    const ew = new Date(sw)
    ew.setDate(sw.getDate() + 7)
    return d >= sw && d < ew
  }
  // mes
  return (
    d.getMonth() === today.getMonth() && d.getFullYear() === today.getFullYear()
  )
}

const DATE_TABS: { key: DateFilter; label: string }[] = [
  { key: "hoje",   label: "Hoje" },
  { key: "semana", label: "Esta semana" },
  { key: "mes",    label: "Este mês" },
  { key: "todos",  label: "Todos" },
]

const STATUS_OPTIONS = [
  "todos",
  "SCHEDULED",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
  "NO_SHOW",
]

const TERMINAL = new Set(["CANCELLED", "NO_SHOW", "COMPLETED"])

// ── Componente ───────────────────────────────────────────────────────────────

export default function AppointmentsPage() {
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filtros
  const [dateFilter, setDateFilter] = useState<DateFilter>("hoje")
  const [profFilter, setProfFilter] = useState("todos")
  const [statusFilter, setStatusFilter] = useState("todos")

  // Remarcar dialog
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt, setNewStartAt] = useState("")
  const [rescheduling, setRescheduling] = useState(false)

  async function fetchAll() {
    try {
      setLoading(true)
      const [appts, profs] = await Promise.all([
        api.get<Appointment[]>("/appointments/"),
        api.get<Professional[]>("/professionals/"),
      ])
      setAppointments(appts)
      setProfessionals(profs)
    } catch {
      setError("Não foi possível carregar os agendamentos.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  // Filtro client-side (API retorna todos)
  const filtered = useMemo(() => {
    return appointments
      .filter((a) => matchesDate(a.start_at, dateFilter))
      .filter((a) => profFilter   === "todos" || a.professional_id === profFilter)
      .filter((a) => statusFilter === "todos" || a.status === statusFilter)
  }, [appointments, dateFilter, profFilter, statusFilter])

  // ── Ações ──────────────────────────────────────────────────────────────────

  async function handleComplete(id: string) {
    if (!confirm("Marcar como concluído? O cliente receberá uma mensagem de agradecimento.")) return
    try {
      await api.patch(`/appointments/${id}/complete`, {})
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
  }

  async function handleCancel(id: string) {
    if (!confirm("Cancelar este agendamento?")) return
    try {
      await api.patch(`/appointments/${id}/cancel`, { reason: "Cancelado pelo painel" })
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
  }

  async function handleReschedule() {
    if (!rescheduleId || !newStartAt) return
    setRescheduling(true)
    try {
      await api.patch(`/appointments/${rescheduleId}/reschedule`, {
        start_at: new Date(newStartAt).toISOString(),
      })
      setRescheduleId(null)
      setNewStartAt("")
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    } finally {
      setRescheduling(false)
    }
  }

  // ── Labels para selects ────────────────────────────────────────────────────

  const profLabel = profFilter === "todos"
    ? "Todos os profissionais"
    : (professionals.find((p) => p.id === profFilter)?.name ?? "")

  const statusLabel = statusFilter === "todos"
    ? "Todos os status"
    : (APPOINTMENT_STATUS_LABELS[statusFilter] ?? statusFilter)

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error)   return <p className="text-destructive">{error}</p>

  return (
    <div>
      {/* Cabeçalho */}
      <div className="flex items-center justify-between mb-5">
        <h1 className="text-2xl font-bold">Agendamentos</h1>
        <Button onClick={() => router.push("/appointments/new")}>
          + Novo Agendamento
        </Button>
      </div>

      {/* Barra de filtros */}
      <div className="flex flex-wrap items-center gap-3 mb-5">
        {/* Filtro de data — botões agrupados */}
        <div className="flex rounded-lg border overflow-hidden text-sm">
          {DATE_TABS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setDateFilter(key)}
              className={
                "px-3 py-1.5 font-medium transition-colors border-r last:border-r-0 " +
                (dateFilter === key
                  ? "bg-primary text-primary-foreground"
                  : "bg-white text-muted-foreground hover:bg-muted")
              }
            >
              {label}
            </button>
          ))}
        </div>

        {/* Filtro de profissional */}
        <Select
          value={profFilter}
          onValueChange={(v) => v && setProfFilter(v)}
        >
          <SelectTrigger className="w-52">
            <span className={profFilter !== "todos" ? "text-foreground" : "text-muted-foreground"}>
              {profLabel}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos os profissionais</SelectItem>
            {professionals.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Filtro de status */}
        <Select
          value={statusFilter}
          onValueChange={(v) => v && setStatusFilter(v)}
        >
          <SelectTrigger className="w-44">
            <span className={statusFilter !== "todos" ? "text-foreground" : "text-muted-foreground"}>
              {statusLabel}
            </span>
          </SelectTrigger>
          <SelectContent>
            {STATUS_OPTIONS.map((s) => (
              <SelectItem key={s} value={s}>
                {s === "todos" ? "Todos os status" : (APPOINTMENT_STATUS_LABELS[s] ?? s)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        {/* Contador */}
        <span className="ml-auto text-sm text-muted-foreground">
          {filtered.length} resultado{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Tabela */}
      {filtered.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">
          Nenhum agendamento encontrado para os filtros selecionados.
        </p>
      ) : (
        <div className="rounded-xl border bg-white overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data / Hora</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Serviço(s)</TableHead>
                <TableHead>Profissional</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Valor</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((a) => {
                const terminal = TERMINAL.has(a.status)
                return (
                  <TableRow key={a.id}>
                    <TableCell className="whitespace-nowrap font-medium">
                      {formatDateTime(a.start_at)}
                    </TableCell>

                    <TableCell>
                      <div className="font-medium">{a.customer?.name ?? "—"}</div>
                      <div className="text-xs text-muted-foreground">
                        {a.customer?.phone}
                      </div>
                    </TableCell>

                    <TableCell className="text-sm max-w-44">
                      {a.services.map((s) => s.service_name).join(", ")}
                    </TableCell>

                    <TableCell>{a.professional?.name ?? "—"}</TableCell>

                    <TableCell>
                      <Badge
                        variant={
                          (APPOINTMENT_STATUS_VARIANT[a.status] as
                            | "default"
                            | "secondary"
                            | "destructive"
                            | "outline"
                            | undefined) ?? "outline"
                        }
                      >
                        {APPOINTMENT_STATUS_LABELS[a.status] ?? a.status}
                      </Badge>
                    </TableCell>

                    <TableCell className="text-right whitespace-nowrap">
                      {formatBRL(Number(a.total_amount))}
                    </TableCell>

                    <TableCell className="text-right">
                      {!terminal && (
                        <div className="flex gap-1 justify-end">
                          <Button
                            size="sm"
                            variant="default"
                            title="Concluir"
                            onClick={() => handleComplete(a.id)}
                          >
                            ✅
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            title="Remarcar"
                            onClick={() => {
                              setRescheduleId(a.id)
                              setNewStartAt(a.start_at.slice(0, 16))
                            }}
                          >
                            🔄
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            title="Cancelar"
                            onClick={() => handleCancel(a.id)}
                          >
                            ✕
                          </Button>
                        </div>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Dialog de reagendamento */}
      <Dialog
        open={!!rescheduleId}
        onOpenChange={(open) => !open && setRescheduleId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remarcar Agendamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="new-start-at">Novo horário</Label>
            <Input
              id="new-start-at"
              type="datetime-local"
              value={newStartAt}
              onChange={(e) => setNewStartAt(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRescheduleId(null)}>
              Cancelar
            </Button>
            <Button onClick={handleReschedule} disabled={rescheduling}>
              {rescheduling ? "Salvando…" : "Confirmar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
