"use client"

import { formatBRL } from "@/lib/utils"

// ─── Tipos ────────────────────────────────────────────────────────────────────

export interface Appointment {
  id: string
  client_name: string
  service_name: string
  professional_name: string
  start_at: string             // ISO 8601
  end_at: string               // ISO 8601
  status: "SCHEDULED" | "COMPLETED" | "CANCELLED" | "NO_SHOW"
  price?: number
}

interface AgendaCalendarProps {
  appointments: Appointment[]
  professionals: { id: string; name: string; specialty?: string }[]
  date: Date
  companyTimezone?: string
  onAppointmentClick?: (appt: Appointment) => void
  onSlotClick?: (date: Date, professionalId?: string) => void
}

// ─── Constantes ───────────────────────────────────────────────────────────────

const START_HOUR = 7            // 07:00
const END_HOUR   = 22           // exclusivo → última linha 21:00

// O estado é comunicado por opacidade/risco — a cor do bloco é única (accent).
const STATUS_STYLES: Record<string, string> = {
  SCHEDULED: "",
  COMPLETED: "opacity-70",
  CANCELLED: "opacity-40 line-through",
  NO_SHOW:   "opacity-50",
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

// ─── Componente ───────────────────────────────────────────────────────────────
//
// Layout em CSS grid (uma linha por hora). O container cresce com as linhas — não
// há scroll interno vertical nem cabeçalho fixo, então nada fica escondido. Em
// telas estreitas o container rola só na horizontal (min-w mantém a leitura), de
// modo que o mesmo calendário serve desktop e mobile.

export default function AgendaCalendar({
  appointments,
  professionals,
  date,
  onAppointmentClick,
  onSlotClick,
}: AgendaCalendarProps) {
  const dayAppts = appointments.filter((a) => isSameDay(new Date(a.start_at), date))
  const hours = Array.from({ length: END_HOUR - START_HOUR }, (_, i) => START_HOUR + i)

  const columns = `64px repeat(${professionals.length}, minmax(0, 1fr))`
  const minWidth = Math.max(560, 64 + professionals.length * 160)

  function handleSlot(hour: number, professionalId: string) {
    const d = new Date(date)
    d.setHours(hour, 0, 0, 0)
    onSlotClick?.(d, professionalId)
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-card">
      <div style={{ minWidth }}>

        {/* Cabeçalho — HORA + profissionais */}
        <div className="grid border-b border-border" style={{ gridTemplateColumns: columns }}>
          <div className="flex items-center justify-center px-2 py-3 text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
            Hora
          </div>
          {professionals.map((prof) => (
            <div key={prof.id} className="border-l border-border px-3 py-3 text-center">
              <p className="truncate text-lg font-semibold leading-tight text-foreground [font-family:var(--font-display)]">
                {prof.name}
              </p>
              {prof.specialty && (
                <p className="truncate text-xs text-muted-foreground">{prof.specialty}</p>
              )}
            </div>
          ))}
        </div>

        {/* Uma linha por hora — a altura acompanha o conteúdo */}
        {hours.map((h) => (
          <div
            key={h}
            className="grid border-b border-border last:border-b-0"
            style={{ gridTemplateColumns: columns }}
          >
            <div className="px-2 py-2 text-right font-mono text-xs text-muted-foreground">
              {String(h).padStart(2, "0")}:00
            </div>
            {professionals.map((prof) => {
              const slot = dayAppts.filter(
                (a) => a.professional_name === prof.name && new Date(a.start_at).getHours() === h,
              )
              return (
                <div
                  key={prof.id}
                  className="min-h-[64px] space-y-1 border-l border-border p-1 transition-colors hover:bg-muted/20"
                  onClick={() => slot.length === 0 && handleSlot(h, prof.id)}
                >
                  {slot.map((a) => (
                    <button
                      key={a.id}
                      onClick={(e) => { e.stopPropagation(); onAppointmentClick?.(a) }}
                      title={`${a.client_name} · ${a.service_name}`}
                      className={`block w-full rounded-md border-l-4 border-primary bg-primary/10 px-2 py-1.5 text-left text-primary transition-colors hover:bg-primary/20 focus:outline-none focus:ring-2 focus:ring-ring ${STATUS_STYLES[a.status] ?? ""}`}
                    >
                      <p className="truncate text-xs font-semibold leading-tight">{a.client_name}</p>
                      <p className="truncate text-[10px] leading-tight text-primary/80">{a.service_name}</p>
                      <div className="mt-0.5 flex items-center justify-between gap-1">
                        <span className="font-mono text-[10px] text-primary/70">{formatTime(a.start_at)}</span>
                        {a.price != null && (
                          <span className="font-mono text-[10px] text-primary/70">{formatBRL(a.price)}</span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              )
            })}
          </div>
        ))}
      </div>
    </div>
  )
}
