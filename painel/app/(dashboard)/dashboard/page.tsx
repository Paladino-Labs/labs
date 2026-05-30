"use client"

import { useEffect, useState, useMemo } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import { APPOINTMENT_STATUS_LABELS } from "@/lib/constants"
import type { Appointment } from "@/types"
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
import { useAuth } from "@/hooks/useAuth"

const TERMINAL = new Set(["CANCELLED", "NO_SHOW", "COMPLETED"])

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return "Bom dia"
  if (h < 18) return "Boa tarde"
  return "Boa noite"
}

function isToday(isoStr: string): boolean {
  const d = new Date(isoStr)
  const now = new Date()
  return (
    d.getDate() === now.getDate() &&
    d.getMonth() === now.getMonth() &&
    d.getFullYear() === now.getFullYear()
  )
}

function fmtHour(isoStr: string): string {
  return new Date(isoStr).toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })
}


export default function DashboardPage() {
  const router = useRouter()
  const { email } = useAuth()

  const [appointments, setAppointments] = useState<Appointment[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [detailAppt, setDetailAppt] = useState<Appointment | null>(null)
  const [rescheduleId, setRescheduleId] = useState<string | null>(null)
  const [newStartAt, setNewStartAt] = useState("")
  const [rescheduling, setRescheduling] = useState(false)

  async function fetchAll() {
    try {
      setLoading(true)
      const appts = await api.get<Appointment[]>("/appointments/")
      setAppointments(appts)
    } catch {
      setError("Não foi possível carregar os dados.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAll() }, [])

  // ── KPI derivations ──────────────────────────────────────────────────────────
  const todayAppts = useMemo(
    () => appointments.filter((a) => isToday(a.start_at)),
    [appointments],
  )

  const todayRevenue = useMemo(
    () =>
      todayAppts
        .filter((a) => a.status === "COMPLETED")
        .reduce((sum, a) => sum + Number(a.total_amount), 0),
    [todayAppts],
  )

  const upcomingToday = useMemo(
    () =>
      todayAppts
        .filter((a) => !TERMINAL.has(a.status))
        .sort(
          (a, b) =>
            new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
        ),
    [todayAppts],
  )

  const topServices = useMemo(() => {
    const now = new Date()
    const counts: Record<string, number> = {}
    appointments
      .filter((a) => {
        const d = new Date(a.start_at)
        return (
          d.getMonth() === now.getMonth() &&
          d.getFullYear() === now.getFullYear()
        )
      })
      .forEach((a) => {
        a.services.forEach((s) => {
          counts[s.service_name] = (counts[s.service_name] ?? 0) + 1
        })
      })
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
  }, [appointments])

  const maxServiceCount = topServices[0]?.[1] ?? 1

  // ── Actions ──────────────────────────────────────────────────────────────────
  async function handleComplete(id: string) {
    if (!confirm("Marcar como concluído?")) return
    try {
      await api.patch(`/appointments/${id}/complete`, {})
      setDetailAppt(null)
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
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

  function openReschedule(a: Appointment) {
    setDetailAppt(null)
    setRescheduleId(a.id)
    const d = new Date(a.start_at)
    const pad = (n: number) => String(n).padStart(2, "0")
    setNewStartAt(
      `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
        `T${pad(d.getHours())}:${pad(d.getMinutes())}`,
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
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    } finally {
      setRescheduling(false)
    }
  }

  // ── Derived display ──────────────────────────────────────────────────────────
  const rawName = email?.split("@")[0]?.split(/[._]/)[0] ?? "Mestre"
  const firstName =
    rawName.charAt(0).toUpperCase() + rawName.slice(1).toLowerCase()

  const kpis = [
    {
      label: "Agendamentos Hoje",
      value: loading ? "…" : String(todayAppts.length),
      hint: `${upcomingToday.length} ainda por vir`,
    },
    {
      label: "Faturamento Hoje",
      value: loading ? "…" : formatBRL(todayRevenue),
      hint: "agendamentos concluídos",
    },
    { label: "Ocupação", value: "—", hint: "em breve" },
    { label: "NPS", value: "—", hint: "em breve" },
  ]

  if (error) return <p className="text-destructive">{error}</p>

  return (
    <div className="flex flex-col gap-8">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div className="flex flex-col gap-3">
        <div className="flex items-center gap-3 text-[11px] uppercase tracking-[0.32em] text-primary/85">
          <span className="h-px w-8 bg-primary/50" />
          <span>Overview · {format(new Date(), "EEEE, d 'de' MMMM", { locale: ptBR })}</span>
          <span className="h-px w-8 bg-primary/50" />
        </div>
        <h1 className="font-display text-5xl md:text-6xl tracking-tight">
          {greeting()}, <em>{firstName}.</em>
        </h1>
      </div>

      {/* ── KPI strip ──────────────────────────────────────────────────────── */}
      <section className="grid grid-cols-1 gap-px overflow-hidden rounded-md border border-border bg-border sm:grid-cols-2 lg:grid-cols-4">
        {kpis.map(({ label, value, hint }) => (
          <div key={label} className="bg-card px-7 py-6">
            <p className="text-[10px] uppercase tracking-[0.25em] text-primary/85">
              {label}
            </p>
            <p className="mt-3 font-display text-5xl leading-none tracking-tight">
              {value}
            </p>
            <p className="mt-3 text-xs italic text-muted-foreground">{hint}</p>
          </div>
        ))}
      </section>

      {/* ── Two-column body ─────────────────────────────────────────────────── */}
      <section className="grid grid-cols-1 gap-6 lg:grid-cols-[2fr_1fr]">

        {/* Upcoming list */}
        <section className="rounded-md border border-border bg-card">
          <div className="flex items-center justify-between px-6 py-4 border-b border-border">
            <h2 className="font-display text-3xl tracking-wide">Próximos da casa</h2>
            <Link
              href="/appointments"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              ver agenda →
            </Link>
          </div>

          {loading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              Carregando…
            </p>
          ) : upcomingToday.length === 0 ? (
            <p className="px-6 py-8 text-sm italic text-muted-foreground">
              Nenhum agendamento pendente para hoje.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {upcomingToday.map((a) => (
                <li
                  key={a.id}
                  onClick={() => setDetailAppt(a)}
                  className="grid grid-cols-[80px_1fr_auto] items-center gap-4 px-6 py-4 cursor-pointer hover:bg-accent/30 transition-colors"
                >
                  <span className="font-display text-2xl italic text-muted-foreground leading-none">
                    {fmtHour(a.start_at)}
                  </span>
                  <div className="min-w-0">
                    <p className="font-display text-xl leading-tight">
                      {a.customer?.name ?? "Cliente"}
                    </p>
                    <p className="text-xs italic text-muted-foreground mt-0.5">
                      {a.services.map((s) => s.service_name).join(", ")}
                      {a.professional && ` · ${a.professional.name}`}
                    </p>
                  </div>
                  <span className="border border-primary/40 px-2 py-0.5 text-[10px] uppercase tracking-[0.22em] text-primary rounded-sm whitespace-nowrap">
                    {APPOINTMENT_STATUS_LABELS[a.status] ?? a.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* Top services */}
        <section className="rounded-md border border-border bg-card">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="font-display text-3xl tracking-wide">Top serviços</h2>
            <p className="text-xs italic text-muted-foreground mt-0.5">
              este mês
            </p>
          </div>

          {loading ? (
            <p className="px-6 py-8 text-sm text-muted-foreground">
              Carregando…
            </p>
          ) : topServices.length === 0 ? (
            <p className="px-6 py-8 text-sm italic text-muted-foreground">
              Sem dados este mês.
            </p>
          ) : (
            <ul className="px-6 py-5 space-y-4">
              {topServices.map(([name, count]) => (
                <li key={name} className="space-y-1.5">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="font-display text-lg leading-tight truncate">
                      {name}
                    </span>
                    <span className="font-display text-sm italic text-muted-foreground flex-shrink-0">
                      {count}×
                    </span>
                  </div>
                  <div className="h-px w-full bg-border overflow-hidden">
                    <div
                      className="h-px bg-primary"
                      style={{
                        width: `${(count / maxServiceCount) * 100}%`,
                      }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

      </section>

      {/* ── Quick action ─────────────────────────────────────────────────────── */}
      <div className="flex justify-end">
        <Button onClick={() => router.push("/appointments/new")}>
          + Novo Agendamento
        </Button>
      </div>

      {/* ── Detail modal ─────────────────────────────────────────────────────── */}
      <Dialog
        open={!!detailAppt}
        onOpenChange={(open) => !open && setDetailAppt(null)}
      >
        {detailAppt && (
          <DialogContent className="max-w-sm">
            <DialogHeader>
              <DialogTitle>
                {detailAppt.customer?.name ?? "Cliente"}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-3 py-1">
              <span className="inline-block border border-primary/40 px-2 py-0.5 text-[10px] uppercase tracking-[0.22em] text-primary rounded-sm">
                {APPOINTMENT_STATUS_LABELS[detailAppt.status] ??
                  detailAppt.status}
              </span>
              <div className="space-y-1.5 text-sm text-muted-foreground">
                <div>{fmtHour(detailAppt.start_at)}</div>
                <div>
                  {detailAppt.services
                    .map((s) => s.service_name)
                    .join(", ")}
                </div>
                <div>{detailAppt.professional?.name ?? "—"}</div>
                {detailAppt.customer?.phone && (
                  <div>{detailAppt.customer.phone}</div>
                )}
                {detailAppt.total_amount && (
                  <div className="font-semibold text-foreground">
                    {formatBRL(Number(detailAppt.total_amount))}
                  </div>
                )}
              </div>
            </div>
            {!TERMINAL.has(detailAppt.status) && (
              <DialogFooter className="flex gap-2 sm:justify-start">
                <Button
                  size="sm"
                  onClick={() => handleComplete(detailAppt.id)}
                >
                  Concluir
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => openReschedule(detailAppt)}
                >
                  Remarcar
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={() => handleCancel(detailAppt.id)}
                >
                  Cancelar
                </Button>
              </DialogFooter>
            )}
          </DialogContent>
        )}
      </Dialog>

      {/* ── Reschedule dialog ────────────────────────────────────────────────── */}
      <Dialog
        open={!!rescheduleId}
        onOpenChange={(open) => !open && setRescheduleId(null)}
      >
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
