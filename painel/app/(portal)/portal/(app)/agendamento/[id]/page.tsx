"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import {
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  CircleX,
  Loader2,
  MapPin,
  Phone,
  Scissors,
  UserRound,
} from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import {
  type PortalAppointmentDetail,
  type PortalCancelResult,
  type PortalRescheduleResult,
} from "@/lib/portal-types"
import { AppointmentStatusBadge } from "@/components/portal/PortalStatusBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type Load = "loading" | "ok" | "error" | "not-found"

// ── Fuso da empresa ───────────────────────────────────────────────────────────
// O cliente do portal pode estar em fuso diferente do estabelecimento.
// `new Date("YYYY-MM-DDTHH:mm")` interpretaria o wall-clock no fuso do BROWSER
// e deslocaria o horário; aqui o instante é resolvido no fuso da EMPRESA
// (company_timezone do payload) via Intl e serializado em UTC — nunca naive.

function tzOffsetMs(utcMs: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone,
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(new Date(utcMs))
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value)
  // alguns runtimes formatam meia-noite como "24"
  return (
    Date.UTC(get("year"), get("month") - 1, get("day"), get("hour") % 24, get("minute"), get("second")) -
    utcMs
  )
}

function zonedWallClockToISO(date: string, time: string, timeZone: string): string | null {
  const [y, mo, d] = date.split("-").map(Number)
  const [h, mi] = time.split(":").map(Number)
  if ([y, mo, d, h, mi].some((n) => n == null || Number.isNaN(n))) return null
  const wallUTC = Date.UTC(y, mo - 1, d, h, mi)
  try {
    // 2 passadas convergem mesmo com transição de DST próxima ao instante
    let utc = wallUTC
    for (let i = 0; i < 2; i++) utc = wallUTC - tzOffsetMs(utc, timeZone)
    return new Date(utc).toISOString()
  } catch {
    // timeZone inválido → interpreta no fuso local (ainda não-naive: tem offset)
    const local = new Date(y, mo - 1, d, h, mi)
    return isNaN(local.getTime()) ? null : local.toISOString()
  }
}

// ── Página ────────────────────────────────────────────────────────────────────

export default function PortalAgendamentoDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [state, setState] = useState<Load>("loading")
  const [detail, setDetail] = useState<PortalAppointmentDetail | null>(null)

  // Resultado da última ação (banner de sucesso no detalhe)
  const [notice, setNotice] = useState<{ text: string; depositRetained: boolean } | null>(null)

  // Dialog cancelar
  const [cancelOpen, setCancelOpen] = useState(false)
  const [cancelError, setCancelError] = useState<string | null>(null)

  // Dialog remarcar
  const [rescheduleOpen, setRescheduleOpen] = useState(false)
  const [rescheduleError, setRescheduleError] = useState<string | null>(null)
  const [newDate, setNewDate] = useState("")
  const [newTime, setNewTime] = useState("")

  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(() => {
    setState("loading")
    portal
      .get<PortalAppointmentDetail>(`/portal/appointments/${id}`)
      .then((d) => {
        setDetail(d)
        setState("ok")
      })
      .catch((err: unknown) => {
        // 404 genérico do backend (agendamento inexistente ou de outra identity)
        setState((err as { status?: number }).status === 404 ? "not-found" : "error")
      })
  }, [id])

  useEffect(() => {
    load()
  }, [load])

  async function handleCancel() {
    setSubmitting(true)
    setCancelError(null)
    try {
      const res = await portal.post<PortalCancelResult>(`/portal/appointments/${id}/cancel`)
      setCancelOpen(false)
      setNotice({ text: "Agendamento cancelado", depositRetained: res.deposit_retained })
      // Reflete o novo status (Cancelado, sem botões de ação)
      setDetail((d) =>
        d ? { ...d, status: res.status, can_cancel: false, can_reschedule: false } : d,
      )
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setCancelError(
        status === 422
          ? ((err as { message?: string }).message ?? "Este agendamento não pode ser cancelado.")
          : "Não foi possível cancelar. Tente novamente.",
      )
    } finally {
      setSubmitting(false)
    }
  }

  async function handleReschedule() {
    if (!detail || !newDate || !newTime) return
    const startAt = zonedWallClockToISO(newDate, newTime, detail.company_timezone)
    if (!startAt) {
      setRescheduleError("Data ou hora inválida.")
      return
    }
    setSubmitting(true)
    setRescheduleError(null)
    try {
      const res = await portal.post<PortalRescheduleResult>(
        `/portal/appointments/${id}/reschedule`,
        { start_at: startAt },
      )
      setRescheduleOpen(false)
      setNotice({
        text: `Agendamento remarcado para ${formatDateTime(res.start_at, detail.company_timezone)}`,
        depositRetained: false,
      })
      // Refetch: novo start_at/end_at vêm do backend (novo manage_token +
      // WhatsApp já disparados lá — nada a fazer aqui)
      load()
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      setRescheduleError(
        status === 422
          ? ((err as { message?: string }).message ??
              "Este horário não está disponível. Escolha outro.")
          : "Não foi possível remarcar. Tente novamente.",
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          size="sm"
          className="h-8 gap-1 px-2"
          onClick={() => router.back()}
        >
          <ChevronLeft size={14} strokeWidth={1.5} /> Voltar
        </Button>
        <h1 className="font-display text-3xl tracking-wide text-foreground">Agendamento</h1>
      </div>

      {state === "loading" && <Skeleton className="h-96 w-full rounded-xl" />}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "not-found" && (
        <EmptyState
          title="Agendamento não encontrado"
          description="Este agendamento não existe ou não pertence à sua conta."
        />
      )}

      {state === "ok" && detail && (
        <div className="rounded-xl bg-card p-5 ring-1 ring-foreground/10">
          {/* Cabeçalho: empresa + status */}
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-xs uppercase tracking-widest text-primary">
                {detail.company_name ?? "Estabelecimento"}
              </p>
              <div className="mt-1 space-y-0.5">
                {detail.services.length === 0 ? (
                  <h2 className="font-display text-2xl leading-tight text-foreground">
                    Atendimento
                  </h2>
                ) : (
                  detail.services.map((s, i) => (
                    <div key={i}>
                      <h2 className="font-display text-2xl leading-tight text-foreground">
                        {s.service_name}
                      </h2>
                      <p className="text-xs text-muted-foreground">{s.duration_minutes} min</p>
                    </div>
                  ))
                )}
              </div>
            </div>
            <AppointmentStatusBadge status={detail.status} />
          </div>

          {/* Banner de resultado de ação */}
          {notice && (
            <div className="mt-4 space-y-2 rounded-lg border border-border bg-background/50 p-3">
              <p className="flex items-center gap-2 text-sm text-foreground">
                <CheckCircle2 size={14} strokeWidth={1.5} className="shrink-0 text-primary" />
                {notice.text}
              </p>
              {notice.depositRetained && (
                <p className="flex items-start gap-2 text-xs text-amber-700 dark:text-amber-300">
                  <AlertTriangle size={14} strokeWidth={1.5} className="mt-0.5 shrink-0" />
                  O sinal pago não será reembolsado por estar fora do prazo de cancelamento.
                </p>
              )}
            </div>
          )}

          {/* Data/hora · profissional · total */}
          <div className="mt-4 space-y-3 border-t border-border pt-4 text-sm text-foreground">
            <p className="flex items-start gap-2">
              <CalendarClock
                size={14}
                strokeWidth={1.5}
                className="mt-0.5 shrink-0 text-muted-foreground"
              />
              {formatDateTime(detail.start_at, detail.company_timezone)}
            </p>
            {detail.professional_name && (
              <p className="flex items-start gap-2">
                <UserRound
                  size={14}
                  strokeWidth={1.5}
                  className="mt-0.5 shrink-0 text-muted-foreground"
                />
                com {detail.professional_name}
              </p>
            )}
            <p className="flex items-start gap-2">
              <Scissors
                size={14}
                strokeWidth={1.5}
                className="mt-0.5 shrink-0 text-muted-foreground"
              />
              Total: {formatBRLFromDecimal(detail.total_amount)}
            </p>
          </div>

          {/* Endereço */}
          <div className="mt-4 space-y-2 border-t border-border pt-4 text-sm">
            <p className="font-medium text-foreground">
              {detail.company_name ?? "Estabelecimento"}
            </p>
            {(detail.company_address || detail.company_city) && (
              <p className="flex items-start gap-2 text-foreground">
                <MapPin
                  size={14}
                  strokeWidth={1.5}
                  className="mt-0.5 shrink-0 text-muted-foreground"
                />
                {[detail.company_address, detail.company_city].filter(Boolean).join(" · ")}
              </p>
            )}
            {detail.company_whatsapp && (
              <p className="flex items-start gap-2 text-foreground">
                <Phone
                  size={14}
                  strokeWidth={1.5}
                  className="mt-0.5 shrink-0 text-muted-foreground"
                />
                {detail.company_whatsapp}
              </p>
            )}
            {detail.company_maps_url && (
              <a
                href={detail.company_maps_url}
                target="_blank"
                rel="noreferrer"
                className="inline-block text-xs text-primary hover:underline"
              >
                Ver no mapa →
              </a>
            )}
          </div>

          {/* Ações */}
          {(detail.can_reschedule || detail.can_cancel) && (
            <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border pt-4">
              {detail.can_reschedule && (
                <Button
                  className="min-h-9"
                  onClick={() => {
                    setRescheduleError(null)
                    setNewDate("")
                    setNewTime("")
                    setRescheduleOpen(true)
                  }}
                >
                  Remarcar
                </Button>
              )}
              {detail.can_cancel && (
                <Button
                  variant="ghost"
                  className="min-h-9 text-destructive hover:bg-destructive/10 hover:text-destructive"
                  onClick={() => {
                    setCancelError(null)
                    setCancelOpen(true)
                  }}
                >
                  <CircleX size={14} strokeWidth={1.5} /> Cancelar
                </Button>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── Dialog: cancelar (Dialog — projeto não tem AlertDialog) ─────────── */}
      <Dialog open={cancelOpen} onOpenChange={(o) => !submitting && !o && setCancelOpen(false)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar agendamento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Tem certeza que deseja cancelar este agendamento?
          </p>
          {cancelError && <p className="text-sm text-destructive">{cancelError}</p>}
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

      {/* ── Dialog: remarcar ────────────────────────────────────────────────── */}
      <Dialog
        open={rescheduleOpen}
        onOpenChange={(o) => !submitting && !o && setRescheduleOpen(false)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remarcar agendamento</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Escolha uma nova data e hora para o seu atendimento.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label htmlFor="reschedule-date" className="text-xs text-muted-foreground">
                Data
              </label>
              <Input
                id="reschedule-date"
                type="date"
                value={newDate}
                disabled={submitting}
                onChange={(e) => setNewDate(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="reschedule-time" className="text-xs text-muted-foreground">
                Hora
              </label>
              <Input
                id="reschedule-time"
                type="time"
                value={newTime}
                disabled={submitting}
                onChange={(e) => setNewTime(e.target.value)}
              />
            </div>
          </div>
          {rescheduleError && <p className="text-sm text-destructive">{rescheduleError}</p>}
          <DialogFooter>
            <Button
              variant="outline"
              disabled={submitting}
              onClick={() => setRescheduleOpen(false)}
            >
              Voltar
            </Button>
            <Button disabled={submitting || !newDate || !newTime} onClick={handleReschedule}>
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
