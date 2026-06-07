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
import { CheckCircle2, ChevronLeft, ChevronRight, RefreshCw, X, LayoutList, CalendarDays } from "lucide-react"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import AgendaCalendar, { type Appointment as CalendarAppt } from "@/components/AgendaCalendar"
import { PaymentOnCompleteDialog } from "@/components/PaymentOnCompleteDialog"

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

const PROF_COLORS = [
  "#7C3AED", "#0891B2", "#059669", "#D97706",
  "#DC2626", "#DB2777", "#2563EB", "#65A30D",
]

function statusToColor(status: string): string {
  const map: Record<string, string> = {
    SCHEDULED:   "#3B82F6",
    REQUESTED:   "#3B82F6",
    DRAFT:       "#6B7280",
    IN_PROGRESS: "#F59E0B",
    COMPLETED:   "#10B981",
    CANCELLED:   "#EF4444",
    NO_SHOW:     "#EF4444",
    FAILED:      "#EF4444",
  }
  return map[status] ?? "#3B82F6"
}

function toCalendarStatus(status: string): CalendarAppt["status"] {
  const allowed = new Set(["SCHEDULED", "COMPLETED", "CANCELLED", "NO_SHOW"])
  if (allowed.has(status)) return status as CalendarAppt["status"]
  return "SCHEDULED"
}

export default function AppointmentsPage() {
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Vista: lista ou calendário
  const [viewMode, setViewMode] = useState<"list" | "calendar">("calendar")

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

  // Modal de detalhe
  const [detailAppt, setDetailAppt] = useState<Appointment | null>(null)

  // Dialog de pagamento ao concluir
  const [paymentTarget, setPaymentTarget] = useState<Appointment | null>(null)

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

  // Mapa profissional → cor
  const profColorMap = useMemo(() => {
    const m = new Map<string, string>()
    professionals.forEach((p, i) => {
      m.set(p.id, PROF_COLORS[i % PROF_COLORS.length])
    })
    return m
  }, [professionals])

  // Dados para o AgendaCalendar
  const calendarAppts = useMemo<CalendarAppt[]>(() => {
    return appointments.map((a) => ({
      id: a.id,
      client_name: a.customer?.name ?? "—",
      service_name: a.services.map((s) => s.service_name).join(", "),
      professional_name: a.professional?.name ?? "—",
      professional_color: statusToColor(a.status),
      start_at: a.start_at,
      end_at: a.end_at,
      status: toCalendarStatus(a.status),
    }))
  }, [appointments])

  const calendarProfessionals = useMemo(() => {
    return professionals.map((p, i) => ({
      id: p.id,
      name: p.name,
      color: PROF_COLORS[i % PROF_COLORS.length],
    }))
  }, [professionals])

  // ── Ações ────────────────────────────────────────────────────────────────────

  function handleComplete(appt: Appointment) {
    setDetailAppt(null)
    setPaymentTarget(appt)
  }

  async function handleCancel(id: string) {
    if (!confirm("Cancelar este agendamento?")) return
    try {
      await api.patch(`/appointments/${id}/cancel`, { reason: "Cancelado pelo painel" })
      setDetailAppt(null)
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
      setDetailAppt(null)
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    } finally {
      setRescheduling(false)
    }
  }

  function openReschedule(a: Appointment) {
    const d = new Date(a.start_at)
    const pad = (n: number) => String(n).padStart(2, "0")
    setRescheduleId(a.id)
    setNewStartAt(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`
    )
    setDetailAppt(null)
  }

  function handleCalendarApptClick(calAppt: CalendarAppt) {
    const appt = appointments.find((a) => a.id === calAppt.id)
    if (appt) setDetailAppt(appt)
  }

  function handleCalendarSlotClick(date: Date, profId?: string) {
    const pad = (n: number) => String(n).padStart(2, "0")
    const startAt =
      `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
      `T${pad(date.getHours())}:${pad(date.getMinutes())}`
    const params = new URLSearchParams()
    if (profId) params.set("professional_id", profId)
    params.set("start_at", startAt)
    router.push(`/appointments/new?${params.toString()}`)
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

          {/* Toggle Lista / Calendário — apenas desktop */}
          <div className="hidden sm:flex rounded-md border border-border overflow-hidden">
            <button
              onClick={() => setViewMode("list")}
              title="Visualização em lista"
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                viewMode === "list"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent"
              )}
            >
              <LayoutList className="h-3.5 w-3.5" />
              Lista
            </button>
            <button
              onClick={() => setViewMode("calendar")}
              title="Visualização em calendário"
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors",
                viewMode === "calendar"
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent"
              )}
            >
              <CalendarDays className="h-3.5 w-3.5" />
              Calendário
            </button>
          </div>

          <Button onClick={() => router.push("/appointments/new")}>
            + Novo Agendamento
          </Button>
        </div>
      </div>

      {/* Visualização Calendário (desktop) */}
      {viewMode === "calendar" && (
        <div className="hidden sm:block" style={{ height: "calc(100vh - 14rem)" }}>
          <AgendaCalendar
            appointments={calendarAppts}
            professionals={calendarProfessionals}
            onAppointmentClick={handleCalendarApptClick}
            onSlotClick={handleCalendarSlotClick}
          />
        </div>
      )}

      {/* Visualização Lista */}
      {(viewMode === "list" || true) && (
        <div className={viewMode === "calendar" ? "sm:hidden" : ""}>

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
          <div className="flex flex-wrap items-center gap-3 mt-4">
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
            <p className="text-center text-muted-foreground py-12 mt-4">
              Nenhum agendamento para este dia.
            </p>
          ) : (
            <div className="rounded-xl border border-border bg-card overflow-hidden mt-4">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Horário</TableHead>
                    <TableHead>Cliente</TableHead>
                    <TableHead>Serviço(s)</TableHead>
                    <TableHead>Barbeiro</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="text-right">Valor</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filtered.map((a) => (
                    <TableRow
                      key={a.id}
                      className="cursor-pointer hover:bg-accent/40"
                      onClick={() => setDetailAppt(a)}
                    >
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
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </div>
      )}

      {/* Modal de detalhe do agendamento */}
      <Dialog open={!!detailAppt} onOpenChange={(open) => !open && setDetailAppt(null)}>
        {detailAppt && (
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Detalhe do Agendamento</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-1">
              <div className="flex items-center gap-2">
                <Badge
                  variant={
                    (APPOINTMENT_STATUS_VARIANT[detailAppt.status] as
                      | "default"
                      | "secondary"
                      | "destructive"
                      | "outline"
                      | undefined) ?? "outline"
                  }
                >
                  {APPOINTMENT_STATUS_LABELS[detailAppt.status] ?? detailAppt.status}
                </Badge>
              </div>

              <div className="rounded-lg border border-border bg-muted/30 p-4 space-y-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Cliente</span>
                  <span className="font-medium text-right">
                    <div>{detailAppt.customer?.name ?? "—"}</div>
                    {detailAppt.customer?.phone && (
                      <div className="text-xs text-muted-foreground font-normal">
                        {detailAppt.customer.phone}
                      </div>
                    )}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Barbeiro</span>
                  <span className="font-medium">{detailAppt.professional?.name ?? "—"}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Serviço(s)</span>
                  <span className="font-medium text-right max-w-48">
                    {detailAppt.services.map((s) => s.service_name).join(", ")}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Horário</span>
                  <span className="font-medium">
                    {formatDateTime(detailAppt.start_at)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-border pt-3 mt-1">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-display text-lg font-semibold">
                    {formatBRL(Number(detailAppt.total_amount))}
                  </span>
                </div>
              </div>
            </div>

            {!TERMINAL.has(detailAppt.status) && (
              <DialogFooter className="flex-wrap gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => openReschedule(detailAppt)}
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Remarcar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleComplete(detailAppt)}
                >
                  <CheckCircle2 className="h-4 w-4 mr-1" />
                  Concluir
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={() => handleCancel(detailAppt.id)}
                >
                  <X className="h-4 w-4 mr-1" />
                  Cancelar
                </Button>
              </DialogFooter>
            )}
          </DialogContent>
        )}
      </Dialog>

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

      {/* Dialog de pagamento ao concluir */}
      <PaymentOnCompleteDialog
        open={paymentTarget !== null}
        appointment={paymentTarget ? {
          id:            paymentTarget.id,
          total_amount:  Number(paymentTarget.total_amount),
          customer_id:   paymentTarget.client_id ?? paymentTarget.customer?.id ?? null,
          customer_name: paymentTarget.customer?.name ?? null,
          services:      paymentTarget.services,
        } : { id: "", total_amount: 0, services: [] }}
        onSuccess={() => { setPaymentTarget(null); fetchAll() }}
        onClose={() => setPaymentTarget(null)}
      />

    </div>
  )
}
