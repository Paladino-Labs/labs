"use client"

import { useEffect, useState, useMemo } from "react"
import { useRouter } from "next/navigation"
import {
  format, startOfWeek, endOfWeek, addDays, isSameDay,
} from "date-fns"
import { ptBR } from "date-fns/locale"
import { api } from "@/lib/api"
import { formatDateTime, formatBRL, cn } from "@/lib/utils"
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
import { CheckCircle2, ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

const STATUS_OPTIONS = [
  "todos",
  "DRAFT",
  "SCHEDULED",
  "REQUESTED",
  "IN_PROGRESS",
  "COMPLETED",
  "CANCELLED",
  "NO_SHOW",
  "FAILED",
]

const TERMINAL = new Set(["CANCELLED", "NO_SHOW", "COMPLETED", "FAILED"])

export default function AppointmentsPage() {
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Navegação de semana
  const [currentDate, setCurrentDate] = useState<Date>(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [selectedDay, setSelectedDay] = useState<Date>(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })

  const weekStart = startOfWeek(currentDate, { weekStartsOn: 0 })
  const weekEnd   = endOfWeek(currentDate, { weekStartsOn: 0 })
  const days      = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))

  function prev() {
    setCurrentDate((d) => addDays(d, -7))
    setSelectedDay((d) => addDays(d, -7))
  }
  function next() {
    setCurrentDate((d) => addDays(d, 7))
    setSelectedDay((d) => addDays(d, 7))
  }
  function goToToday() {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    setCurrentDate(d)
    setSelectedDay(d)
  }

  // Filtros
  const [profFilter,   setProfFilter]   = useState("todos")
  const [statusFilter, setStatusFilter] = useState("todos")

  // Remarcar dialog
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt,   setNewStartAt]   = useState("")
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

  const filtered = useMemo(() => {
    return appointments
      .filter((a) => isSameDay(new Date(a.start_at), selectedDay))
      .filter((a) => profFilter   === "todos" || a.professional_id === profFilter)
      .filter((a) => statusFilter === "todos" || a.status === statusFilter)
  }, [appointments, selectedDay, profFilter, statusFilter])

  // ── Ações ────────────────────────────────────────────────────────────────────

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

  const profLabel   = profFilter   === "todos" ? "Todos os barbeiros"  : (professionals.find((p) => p.id === profFilter)?.name ?? "")
  const statusLabel = statusFilter === "todos" ? "Todos os status"     : (APPOINTMENT_STATUS_LABELS[statusFilter] ?? statusFilter)

  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error)   return <p className="text-destructive">{error}</p>

  return (
    <div className="space-y-5">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-3xl tracking-wide">Agenda</h1>
          <p className="text-sm text-muted-foreground">
            {format(weekStart, "d MMM", { locale: ptBR })} –{" "}
            {format(weekEnd, "d MMM yyyy", { locale: ptBR })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" onClick={prev}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" onClick={goToToday}>Hoje</Button>
          <Button variant="outline" size="icon" onClick={next}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button onClick={() => router.push("/appointments/new")}>
            + Novo Agendamento
          </Button>
        </div>
      </div>

      {/* Day picker — 7 dias da semana */}
      <div className="grid grid-cols-7 gap-2">
        {days.map((d) => {
          const count  = appointments.filter((a) => isSameDay(new Date(a.start_at), d)).length
          const active = isSameDay(d, selectedDay)
          return (
            <button
              key={d.toISOString()}
              onClick={() => setSelectedDay(d)}
              className={cn(
                "flex flex-col items-center rounded-lg border p-3 transition-colors",
                active
                  ? "border-primary bg-primary/10"
                  : "border-border hover:bg-accent"
              )}
            >
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {format(d, "EEE", { locale: ptBR })}
              </span>
              <span className="[font-family:var(--font-display)] text-2xl">{format(d, "d")}</span>
              <span className="text-[10px] text-muted-foreground">{count} agend.</span>
            </button>
          )
        })}
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-3">
        <Select value={profFilter} onValueChange={(v) => v && setProfFilter(v)}>
          <SelectTrigger className="w-52">
            <span className={profFilter !== "todos" ? "text-foreground" : "text-muted-foreground"}>
              {profLabel}
            </span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos os barbeiros</SelectItem>
            {professionals.map((p) => (
              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
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

        <span className="ml-auto text-sm text-muted-foreground">
          {filtered.length} resultado{filtered.length !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Tabela */}
      {filtered.length === 0 ? (
        <p className="text-center text-muted-foreground py-12">
          Nenhum agendamento para este dia.
        </p>
      ) : (
        <div className="rounded-xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Horário</TableHead>
                <TableHead>Cliente</TableHead>
                <TableHead>Serviço(s)</TableHead>
                <TableHead>Barbeiro</TableHead>
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
                            variant="ghost"
                            size="icon"
                            title="Concluir"
                            onClick={() => handleComplete(a.id)}
                          >
                            <CheckCircle2 className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Remarcar"
                            onClick={() => {
                              setRescheduleId(a.id)
                              const d = new Date(a.start_at)
                              const pad = (n: number) => String(n).padStart(2, "0")
                              setNewStartAt(
                                `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
                                `T${pad(d.getHours())}:${pad(d.getMinutes())}`
                              )
                            }}
                          >
                            <RefreshCw className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            title="Cancelar"
                            onClick={() => handleCancel(a.id)}
                          >
                            <X className="h-4 w-4" />
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
