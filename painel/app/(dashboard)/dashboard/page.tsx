"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { APPOINTMENT_STATUS_LABELS, APPOINTMENT_STATUS_VARIANT } from "@/lib/constants"
import type { Appointment } from "@/types"
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


export default function DashboardPage() {
  const router = useRouter()
  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Remarcar
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt, setNewStartAt] = useState("")
  const [rescheduling, setRescheduling] = useState(false)

  async function fetchAppointments() {
    try {
      setLoading(true)
      const data = await api.get<Appointment[]>("/appointments/")
      setAppointments(data)
    } catch {
      setError("Não foi possível carregar os agendamentos.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAppointments() }, [])

  async function handleCancel(id: string) {
    if (!confirm("Cancelar este agendamento?")) return
    try {
      await api.patch(`/appointments/${id}/cancel`, { reason: "Cancelado pelo painel" })
      fetchAppointments()
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
      fetchAppointments()
    } catch (err: unknown) {
      alert((err as Error).message)
    } finally {
      setRescheduling(false)
    }
  }

  // Agrupados por profissional
  const grouped = appointments.reduce<Record<string, Appointment[]>>((acc, a) => {
    const key = a.professional?.name ?? "Sem profissional"
    if (!acc[key]) acc[key] = []
    acc[key].push(a)
    return acc
  }, {})

  if (loading) return <p className="text-muted-foreground">Carregando agenda…</p>
  if (error) return <p className="text-destructive">{error}</p>

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Agenda</h1>
        <Button onClick={() => router.push("/appointments/new")}>
          + Novo Agendamento
        </Button>
      </div>

      {Object.keys(grouped).length === 0 && (
        <p className="text-muted-foreground">Nenhum agendamento encontrado.</p>
      )}

      {Object.entries(grouped).map(([professional, list]) => (
        <div key={professional} className="mb-8">
          <h2 className="text-lg font-semibold mb-3">{professional}</h2>

          <div className="space-y-3">
            {list.map((a) => (
              <div
                key={a.id}
                className="bg-white rounded-lg border p-4 flex items-center justify-between gap-4"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-medium">
                      {formatDateTime(a.start_at)}
                    </span>
                    <Badge variant={APPOINTMENT_STATUS_VARIANT[a.status] ?? "outline"}>
                      {APPOINTMENT_STATUS_LABELS[a.status] ?? a.status}
                    </Badge>
                  </div>

                  <p className="text-sm text-muted-foreground">
                    {a.customer?.name ?? "—"} · {a.customer?.phone ?? ""}
                  </p>

                  <p className="text-sm text-muted-foreground">
                    {a.services.map((s) => s.service_name).join(", ")}
                  </p>
                </div>

                {!["CANCELLED", "NO_SHOW", "COMPLETED"].includes(a.status) && (
                  <div className="flex gap-2 shrink-0">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setRescheduleId(a.id)
                        setNewStartAt(a.start_at.slice(0, 16))
                      }}
                    >
                      Remarcar
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleCancel(a.id)}
                    >
                      Cancelar
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}

      {/* Dialog de reagendamento */}
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
