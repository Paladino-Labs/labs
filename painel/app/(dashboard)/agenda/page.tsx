"use client"

import { useEffect, useState, useMemo } from "react"
import { useRouter } from "next/navigation"
import {
  format, startOfWeek, endOfWeek, addDays, isSameDay,
} from "date-fns"
import { ptBR } from "date-fns/locale"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { formatDateTime, formatBRL, cn } from "@/lib/utils"
import type { Appointment, Professional } from "@/types"
import { ErrorState } from "@/components/ErrorState"
import { AppointmentBadge } from "@/components/FsmBadge"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CheckCircle2, ChevronLeft, ChevronRight, RefreshCw, X } from "lucide-react"
import AgendaCalendar, { type Appointment as CalendarAppt } from "@/components/AgendaCalendar"
import { PaymentOnCompleteDialog } from "@/components/PaymentOnCompleteDialog"

const TERMINAL = new Set(["CANCELLED", "NO_SHOW", "COMPLETED", "FAILED"])

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

  // Modal de detalhe
  const [detailAppt, setDetailAppt] = useState<Appointment | null>(null)

  // Dialog de pagamento ao concluir
  const [paymentTarget, setPaymentTarget] = useState<Appointment | null>(null)

  // Remarcar dialog
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt,   setNewStartAt]   = useState("")
  const [rescheduling, setRescheduling] = useState(false)

  // Cancelar confirmação
  const [cancelTarget, setCancelTarget] = useState<Appointment | null>(null)
  const [cancelling,   setCancelling]   = useState(false)

  async function fetchAll() {
    try {
      setLoading(true)
      // Busca a semana exibida — cobre o dia selecionado, as contagens do
      // day picker e a visão semanal do calendário.
      const params = new URLSearchParams({
        start_after:  weekStart.toISOString(),
        start_before: weekEnd.toISOString(),
        page_size:    "200",
      })
      const [appts, profs] = await Promise.all([
        api.get<Appointment[]>(`/appointments/?${params}`),
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

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchAll() }, [currentDate])

  // Dados para o AgendaCalendar
  const calendarAppts = useMemo<CalendarAppt[]>(() => {
    return appointments.map((a) => ({
      id: a.id,
      client_name: a.customer?.name ?? "—",
      service_name: a.services.map((s) => s.service_name).join(", "),
      professional_name: a.professional?.name ?? "—",
      start_at: a.start_at,
      end_at: a.end_at,
      status: toCalendarStatus(a.status),
      price: Number(a.total_amount),
    }))
  }, [appointments])

  const calendarProfessionals = useMemo(() => {
    return professionals.map((p) => ({
      id: p.id,
      name: p.name,
      specialty: p.specialty ?? p.specialties?.[0],
    }))
  }, [professionals])

  // ── Ações ────────────────────────────────────────────────────────────────────

  function handleComplete(appt: Appointment) {
    setDetailAppt(null)
    setPaymentTarget(appt)
  }

  async function confirmCancel() {
    if (!cancelTarget) return
    setCancelling(true)
    try {
      await api.patch(`/appointments/${cancelTarget.id}/cancel`, { reason: "Cancelado pelo painel" })
      toast.success("Agendamento cancelado")
      setCancelTarget(null)
      fetchAll()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao cancelar")
    } finally {
      setCancelling(false)
    }
  }

  async function handleReschedule() {
    if (!rescheduleId || !newStartAt) return
    setRescheduling(true)
    try {
      await api.patch(`/appointments/${rescheduleId}/reschedule`, {
        start_at: new Date(newStartAt).toISOString(),
      })
      toast.success("Agendamento remarcado")
      setRescheduleId(null)
      setNewStartAt("")
      setDetailAppt(null)
      fetchAll()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao remarcar")
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

  if (loading) return <Skeleton className="h-96 w-full" />
  if (error)   return <ErrorState message={error} onRetry={fetchAll} />

  return (
    <div className="space-y-4">

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
        </div>
      </div>

      {/* Day picker — 7 dias da semana (sempre visível; controla o dia exibido) */}
      <div className="grid grid-cols-7 gap-2">
        {days.map((d) => {
          const count  = appointments.filter((a) => isSameDay(new Date(a.start_at), d)).length
          const active = isSameDay(d, selectedDay)
          return (
            <button
              key={d.toISOString()}
              onClick={() => setSelectedDay(d)}
              className={cn(
                "flex flex-col items-center rounded-lg p-3 transition-colors",
                active
                  ? "border-2 border-primary/40 bg-primary/[0.06] text-foreground"
                  : "border border-border bg-card/60 text-muted-foreground hover:bg-muted/60"
              )}
            >
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                {format(d, "EEE", { locale: ptBR })}
              </span>
              <span className={cn(
                "[font-family:var(--font-display)] text-2xl",
                active ? "text-primary" : "text-foreground"
              )}>{format(d, "d")}</span>
              <span className="text-[10px] text-muted-foreground">{count} agend.</span>
            </button>
          )
        })}
      </div>

      {/* Calendário — responsivo (rola na horizontal em telas estreitas) */}
      <AgendaCalendar
        appointments={calendarAppts}
        professionals={calendarProfessionals}
        date={selectedDay}
        onAppointmentClick={handleCalendarApptClick}
        onSlotClick={handleCalendarSlotClick}
      />

      {/* Modal de detalhe do agendamento */}
      <Dialog open={!!detailAppt} onOpenChange={(open) => !open && setDetailAppt(null)}>
        {detailAppt && (
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Detalhe do Agendamento</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-1">
              <div className="flex items-center gap-2">
                <AppointmentBadge status={detailAppt.status} />
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
                  onClick={() => { setCancelTarget(detailAppt); setDetailAppt(null) }}
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

      {/* Confirmar cancelamento */}
      <Dialog open={!!cancelTarget} onOpenChange={(open) => !open && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar agendamento?</DialogTitle>
            <DialogDescription>
              {cancelTarget?.customer?.name
                ? `O agendamento de ${cancelTarget.customer.name} será cancelado.`
                : "Esta ação cancelará o agendamento."}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCancelTarget(null)}>Voltar</Button>
            <Button variant="destructive" onClick={confirmCancel} disabled={cancelling}>
              {cancelling ? "Cancelando…" : "Cancelar agendamento"}
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
