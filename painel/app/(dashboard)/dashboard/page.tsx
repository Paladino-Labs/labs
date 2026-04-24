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
import AgendaCalendar from "@/components/AgendaCalendar"
import type { Appointment as CalAppt } from "@/components/AgendaCalendar"

// ── Paleta de cores por profissional ─────────────────────────────────────────
const PROF_COLORS = [
  "#7C3AED", "#0D9488", "#EA580C", "#2563EB",
  "#DB2777", "#65A30D", "#D97706", "#DC2626",
]
const profColor = (i: number) => PROF_COLORS[i % PROF_COLORS.length]

const TERMINAL = new Set(["CANCELLED", "NO_SHOW", "COMPLETED"])

const STATUS_COLOR: Record<string, string> = {
  SCHEDULED:   "bg-blue-50 text-blue-700",
  IN_PROGRESS: "bg-amber-50 text-amber-700",
  COMPLETED:   "bg-green-50 text-green-700",
  CANCELLED:   "bg-red-50 text-red-700",
  NO_SHOW:     "bg-gray-100 text-gray-600",
}

// ─────────────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const router = useRouter()

  const [appointments,  setAppointments]  = useState<Appointment[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [loading, setLoading] = useState(true)
  const [error,   setError]   = useState<string | null>(null)

  // Modal de detalhe (clique num evento do calendário)
  const [detailAppt, setDetailAppt] = useState<Appointment | null>(null)

  // Dialog de reagendamento
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt,   setNewStartAt]   = useState("")
  const [rescheduling, setRescheduling] = useState(false)

  // ── Fetch ───────────────────────────────────────────────────────────────────
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

  // ── Mapa de cores estável ───────────────────────────────────────────────────
  const profColorMap = useMemo(() => {
    const map: Record<string, string> = {}
    professionals.forEach((p, i) => { map[p.id] = profColor(i) })
    return map
  }, [professionals])

  // ── Converter para o tipo do calendário ────────────────────────────────────
  const calAppointments = useMemo<CalAppt[]>(() =>
    appointments.map((a) => ({
      id:                 a.id,
      client_name:        a.customer?.name ?? "Cliente",
      service_name:       a.services.map((s) => s.service_name).join(", "),
      professional_name:  a.professional?.name ?? "—",
      professional_color: profColorMap[a.professional_id] ?? PROF_COLORS[0],
      start_at:           a.start_at,
      end_at:             a.end_at,
      status:             a.status as CalAppt["status"],
    })),
  [appointments, profColorMap])

  const calProfessionals = useMemo(() =>
    professionals.map((p) => ({
      id:    p.id,
      name:  p.name,
      color: profColorMap[p.id] ?? PROF_COLORS[0],
    })),
  [professionals, profColorMap])

  // ── Ações ───────────────────────────────────────────────────────────────────
  async function handleComplete(id: string) {
    if (!confirm("Marcar como concluído? O cliente receberá uma mensagem de agradecimento.")) return
    try {
      await api.patch(`/appointments/${id}/complete`, {})
      setDetailAppt(null)
      fetchAll()
    } catch (err: unknown) { alert((err as Error).message) }
  }

  async function handleCancel(id: string) {
    if (!confirm("Cancelar este agendamento?")) return
    try {
      await api.patch(`/appointments/${id}/cancel`, { reason: "Cancelado pelo painel" })
      setDetailAppt(null)
      fetchAll()
    } catch (err: unknown) { alert((err as Error).message) }
  }

  function openReschedule(a: Appointment) {
    setDetailAppt(null)
    setRescheduleId(a.id)
    const d = new Date(a.start_at)
    const pad = (n: number) => String(n).padStart(2, "0")
    setNewStartAt(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
      `T${pad(d.getHours())}:${pad(d.getMinutes())}`
    )
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
    } catch (err: unknown) { alert((err as Error).message) }
    finally { setRescheduling(false) }
  }

  // ── Guards ──────────────────────────────────────────────────────────────────
  if (loading) return <p className="text-muted-foreground">Carregando agenda…</p>
  if (error)   return <p className="text-destructive">{error}</p>

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-5 h-full">

      {/* Cabeçalho */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Agenda</h1>
        <Button onClick={() => router.push("/appointments/new")}>
          + Novo Agendamento
        </Button>
      </div>

      {/* Calendário — ocupa o restante da altura da tela */}
      <div style={{ height: "calc(100vh - 140px)", minHeight: 560 }}>
        <AgendaCalendar
          appointments={calAppointments}
          professionals={calProfessionals}
          onAppointmentClick={(calAppt) => {
            const original = appointments.find((a) => a.id === calAppt.id)
            if (original) setDetailAppt(original)
          }}
          onSlotClick={(date, professionalId) => {
            const query = new URLSearchParams({ start_at: date.toISOString() })
            if (professionalId) query.set("professional_id", professionalId)
            router.push(`/appointments/new?${query.toString()}`)
          }}
        />
      </div>

      {/* ── Modal de detalhe do agendamento ──────────────────────────────────── */}
      <Dialog open={!!detailAppt} onOpenChange={(open) => !open && setDetailAppt(null)}>
        {detailAppt && (
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full flex-shrink-0"
                  style={{ backgroundColor: profColorMap[detailAppt.professional_id] ?? "#9CA3AF" }}
                />
                {detailAppt.customer?.name ?? "Cliente"}
              </DialogTitle>
            </DialogHeader>

            <div className="space-y-3 py-1">
              {/* Status */}
              <span className={`inline-block text-xs font-semibold px-2.5 py-1 rounded-full ${STATUS_COLOR[detailAppt.status] ?? "bg-gray-100 text-gray-600"}`}>
                {APPOINTMENT_STATUS_LABELS[detailAppt.status] ?? detailAppt.status}
              </span>

              {/* Detalhes */}
              <div className="space-y-1.5 text-sm text-muted-foreground">
                <div className="flex items-center gap-2">
                  <span>🕐</span>
                  <span>{formatDateTime(detailAppt.start_at)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span>✂️</span>
                  <span>{detailAppt.services.map((s) => s.service_name).join(", ")}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span>👤</span>
                  <span>{detailAppt.professional?.name ?? "—"}</span>
                </div>
                {detailAppt.customer?.phone && (
                  <div className="flex items-center gap-2">
                    <span>📱</span>
                    <span>{detailAppt.customer.phone}</span>
                  </div>
                )}
                {detailAppt.total_amount && (
                  <div className="flex items-center gap-2">
                    <span>💰</span>
                    <span className="font-semibold text-foreground">
                      {formatBRL(Number(detailAppt.total_amount))}
                    </span>
                  </div>
                )}
              </div>
            </div>

            {/* Ações — só para agendamentos não terminais */}
            {!TERMINAL.has(detailAppt.status) && (
              <DialogFooter className="flex gap-2 sm:justify-start">
                <Button size="sm" variant="default"
                  onClick={() => handleComplete(detailAppt.id)}>
                  ✅ Concluir
                </Button>
                <Button size="sm" variant="outline"
                  onClick={() => openReschedule(detailAppt)}>
                  🔄 Remarcar
                </Button>
                <Button size="sm" variant="destructive"
                  onClick={() => handleCancel(detailAppt.id)}>
                  Cancelar
                </Button>
              </DialogFooter>
            )}
          </DialogContent>
        )}
      </Dialog>

      {/* ── Dialog de reagendamento ───────────────────────────────────────────── */}
      <Dialog open={!!rescheduleId} onOpenChange={(open) => !open && setRescheduleId(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remarcar Agendamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-2 py-2">
            <Label htmlFor="new-start">Novo horário</Label>
            <Input
              id="new-start"
              type="datetime-local"
              value={newStartAt}
              onChange={(e) => setNewStartAt(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRescheduleId(null)}>Cancelar</Button>
            <Button onClick={handleReschedule} disabled={rescheduling}>
              {rescheduling ? "Salvando…" : "Confirmar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}