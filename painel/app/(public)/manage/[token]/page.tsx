"use client"

import { useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { AlertTriangle, CalendarClock, Link2Off, Loader2, Scissors, User } from "lucide-react"
import { publicFetch } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { DateTimePicker } from "@/components/DateTimePicker"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

// ─── Tipos (6 campos — NÃO é AppointmentResponse) ───────────────────────────────

interface ManageDetailsResponse {
  service_name: string | null
  professional_name: string | null
  scheduled_datetime: string
  status: string
  can_cancel: boolean
  can_reschedule: boolean
}

interface ManageCancelResponse {
  status: "CANCELLED"
  deposit_retained: boolean
  message: string
}

interface ManageRescheduleResponse {
  status: string
  scheduled_datetime: string
  message: string
}

// Backend devolve enum inglês; UI traduz no badge.
const STATUS_LABEL: Record<string, string> = {
  SCHEDULED: "Agendado",
  CANCELLED: "Cancelado",
  COMPLETED: "Concluído",
  NO_SHOW: "Não compareceu",
  IN_PROGRESS: "Em andamento",
}

const TZ = "America/Sao_Paulo"

function statusVariant(status: string): "default" | "secondary" | "destructive" {
  if (status === "CANCELLED" || status === "NO_SHOW") return "destructive"
  if (status === "SCHEDULED") return "default"
  return "secondary"
}

type View = "loading" | "error-token" | "active" | "result"

interface ResultState {
  message: string
  depositRetained: boolean
}

export default function ManagePage() {
  const { token } = useParams<{ token: string }>()

  const [view, setView] = useState<View>("loading")
  const [details, setDetails] = useState<ManageDetailsResponse | null>(null)
  const [result, setResult] = useState<ResultState | null>(null)
  const [rateLimited, setRateLimited] = useState(false)

  // Dialogs
  const [cancelOpen, setCancelOpen] = useState(false)
  const [rescheduleOpen, setRescheduleOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [newDatetime, setNewDatetime] = useState("")
  const [rescheduleError, setRescheduleError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    publicFetch<ManageDetailsResponse>(`/manage/${token}`)
      .then((data) => {
        if (!active) return
        setDetails(data)
        setView("active")
      })
      .catch((err: unknown) => {
        if (!active) return
        const status = (err as { status?: number }).status
        if (status === 429) {
          setRateLimited(true)
          setView("active") // mantém estrutura mínima; banner explica
        } else {
          // 404 genérico / expirado / terminal → erro de token
          setView("error-token")
        }
      })
    return () => {
      active = false
    }
  }, [token])

  // ── Cancelar ───────────────────────────────────────────────────────────────
  async function handleCancel() {
    setSubmitting(true)
    setRateLimited(false)
    try {
      const res = await publicFetch<ManageCancelResponse>(`/manage/${token}/cancel`, {
        method: "POST",
      })
      setResult({ message: res.message, depositRetained: res.deposit_retained })
      setCancelOpen(false)
      setView("result")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setCancelOpen(false)
      if (status === 429) {
        setRateLimited(true)
      } else {
        setView("error-token")
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── Remarcar ─────────────────────────────────────────────────────────────────
  async function handleReschedule() {
    if (!newDatetime) return
    setSubmitting(true)
    setRescheduleError(null)
    setRateLimited(false)
    try {
      const iso = new Date(newDatetime).toISOString()
      const res = await publicFetch<ManageRescheduleResponse>(
        `/manage/${token}/reschedule`,
        { method: "POST", body: JSON.stringify({ new_datetime: iso }) },
      )
      setResult({ message: res.message, depositRetained: false })
      setRescheduleOpen(false)
      setView("result")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      if (status === 422) {
        setRescheduleError("Esse horário não está disponível. Escolha outro.")
      } else if (status === 429) {
        setRescheduleOpen(false)
        setRateLimited(true)
      } else {
        setRescheduleOpen(false)
        setView("error-token")
      }
    } finally {
      setSubmitting(false)
    }
  }

  // ── loading ──────────────────────────────────────────────────────────────────
  if (view === "loading") {
    return (
      <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="mt-4 h-4 w-48" />
        <Skeleton className="mt-2 h-4 w-40" />
        <Skeleton className="mt-6 h-10 w-full" />
        <Skeleton className="mt-2 h-10 w-full" />
      </div>
    )
  }

  // ── error-token (404 / expirado / terminal) ──────────────────────────────────
  if (view === "error-token") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-card px-6 py-12 text-center shadow-sm">
        <Link2Off className="h-12 w-12 text-muted-foreground" strokeWidth={1.5} />
        <h1 className="font-display text-2xl tracking-wide">Link inválido ou expirado</h1>
        <p className="max-w-sm text-sm text-muted-foreground">
          Este link de gestão não está mais disponível. Fale com o estabelecimento
          para reagendar.
        </p>
      </div>
    )
  }

  // ── result (após cancelar/remarcar — token terminal, sem volta ao form) ───────
  if (view === "result" && result) {
    return (
      <div
        className={
          result.depositRetained
            ? "flex flex-col items-center gap-3 rounded-2xl border border-amber-500/50 bg-amber-500/5 px-6 py-12 text-center shadow-sm"
            : "flex flex-col items-center gap-3 rounded-2xl border border-border bg-card px-6 py-12 text-center shadow-sm"
        }
      >
        {result.depositRetained && (
          <AlertTriangle className="h-12 w-12 text-amber-600 dark:text-amber-400" strokeWidth={1.5} />
        )}
        <p className="max-w-sm text-sm text-foreground">{result.message}</p>
      </div>
    )
  }

  // ── active ─────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-4">
      {rateLimited && (
        <div className="rounded-lg border border-amber-500/50 bg-amber-500/5 px-4 py-3 text-sm text-amber-700 dark:text-amber-300">
          Muitas tentativas, tente novamente em instantes.
        </div>
      )}

      {details && (
        <div className="rounded-2xl border border-border bg-card p-6 shadow-sm">
          <div className="flex items-center justify-between gap-3">
            <h1 className="font-display text-2xl tracking-wide">Seu agendamento</h1>
            <Badge variant={statusVariant(details.status)}>
              {STATUS_LABEL[details.status] ?? details.status}
            </Badge>
          </div>

          <dl className="mt-6 space-y-4">
            <div className="flex items-start gap-3">
              <Scissors className="mt-0.5 h-4 w-4 shrink-0 text-primary" strokeWidth={1.5} />
              <div>
                <dt className="text-xs text-muted-foreground">Serviço</dt>
                <dd className="text-sm">{details.service_name ?? "—"}</dd>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <User className="mt-0.5 h-4 w-4 shrink-0 text-primary" strokeWidth={1.5} />
              <div>
                <dt className="text-xs text-muted-foreground">Profissional</dt>
                <dd className="text-sm">{details.professional_name ?? "—"}</dd>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <CalendarClock className="mt-0.5 h-4 w-4 shrink-0 text-primary" strokeWidth={1.5} />
              <div>
                <dt className="text-xs text-muted-foreground">Data e hora</dt>
                <dd className="text-sm">{formatDateTime(details.scheduled_datetime, TZ)}</dd>
              </div>
            </div>
          </dl>

          <div className="mt-8 flex flex-col gap-2">
            <Button
              variant="outline"
              className="w-full"
              size="lg"
              disabled={!details.can_reschedule}
              onClick={() => {
                setRescheduleError(null)
                setNewDatetime("")
                setRescheduleOpen(true)
              }}
            >
              Remarcar
            </Button>
            <Button
              variant="destructive"
              className="w-full"
              size="lg"
              disabled={!details.can_cancel}
              onClick={() => setCancelOpen(true)}
            >
              Cancelar
            </Button>
          </div>
        </div>
      )}

      {/* ── Dialog: cancelar ─────────────────────────────────────────────────── */}
      <Dialog open={cancelOpen} onOpenChange={(o) => !submitting && setCancelOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar agendamento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja cancelar este agendamento? Esta ação não pode ser desfeita.
          </p>
          <DialogFooter>
            <Button variant="outline" disabled={submitting} onClick={() => setCancelOpen(false)}>
              Voltar
            </Button>
            <Button variant="destructive" disabled={submitting} onClick={handleCancel}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Cancelando…
                </>
              ) : (
                "Sim, cancelar"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Dialog: remarcar ─────────────────────────────────────────────────── */}
      <Dialog open={rescheduleOpen} onOpenChange={(o) => !submitting && setRescheduleOpen(o)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remarcar agendamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <label htmlFor="manage-new-dt" className="text-sm text-muted-foreground">
              Escolha a nova data e horário
            </label>
            <DateTimePicker
              id="manage-new-dt"
              value={newDatetime}
              onChange={setNewDatetime}
              disabled={submitting}
            />
            {rescheduleError && <p className="text-sm text-destructive">{rescheduleError}</p>}
          </div>
          <DialogFooter>
            <Button variant="outline" disabled={submitting} onClick={() => setRescheduleOpen(false)}>
              Voltar
            </Button>
            <Button disabled={submitting || !newDatetime} onClick={handleReschedule}>
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Remarcando…
                </>
              ) : (
                "Confirmar remarcação"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
