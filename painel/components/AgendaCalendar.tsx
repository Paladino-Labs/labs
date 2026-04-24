"use client"

import { useState, useMemo, useRef, useEffect } from "react"

// ─── Tipos ────────────────────────────────────────────────────────────────────

export interface Appointment {
  id: string
  client_name: string
  service_name: string
  professional_name: string
  professional_color: string   // ex: "#7C3AED"
  start_at: string             // ISO 8601
  end_at: string               // ISO 8601
  status: "SCHEDULED" | "COMPLETED" | "CANCELLED" | "NO_SHOW"
}

interface AgendaCalendarProps {
  appointments: Appointment[]
  professionals: { id: string; name: string; color: string }[]
  companyTimezone?: string
  onAppointmentClick?: (appt: Appointment) => void
  onSlotClick?: (date: Date, professionalId?: string) => void
}

// ─── Constantes ───────────────────────────────────────────────────────────────

const HOUR_HEIGHT = 64          // px por hora
const START_HOUR  = 7           // 07:00
const END_HOUR    = 22          // 22:00
const TOTAL_HOURS = END_HOUR - START_HOUR

const STATUS_STYLES: Record<string, string> = {
  SCHEDULED:  "border-l-4",
  COMPLETED:  "border-l-4 opacity-70",
  CANCELLED:  "border-l-4 opacity-40 line-through",
  NO_SHOW:    "border-l-4 opacity-50",
}

const DAYS_PT = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"]
const MONTHS_PT = [
  "janeiro","fevereiro","março","abril","maio","junho",
  "julho","agosto","setembro","outubro","novembro","dezembro",
]

// ─── Helpers ──────────────────────────────────────────────────────────────────

function startOfWeek(d: Date): Date {
  const day = new Date(d)
  const diff = day.getDay()   // 0 = domingo
  day.setDate(day.getDate() - diff)
  day.setHours(0, 0, 0, 0)
  return day
}

function addDays(d: Date, n: number): Date {
  const r = new Date(d)
  r.setDate(r.getDate() + n)
  return r
}

function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

function topOffsetPct(date: Date): number {
  const mins = (date.getHours() - START_HOUR) * 60 + date.getMinutes()
  return (mins / (TOTAL_HOURS * 60)) * 100
}

function heightPct(start: Date, end: Date): number {
  const mins = (end.getTime() - start.getTime()) / 60000
  return (mins / (TOTAL_HOURS * 60)) * 100
}

function formatHour(h: number): string {
  return `${String(h).padStart(2, "0")}:00`
}

function formatTime(d: Date): string {
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`
}

// ─── Componente de evento ─────────────────────────────────────────────────────

function ApptBlock({
  appt,
  color,
  onClick,
}: {
  appt: Appointment
  color: string
  onClick: () => void
}) {
  const start = new Date(appt.start_at)
  const end   = new Date(appt.end_at)
  const top   = topOffsetPct(start)
  const height = Math.max(heightPct(start, end), 2.5)   // mínimo visível
  const durationMin = (end.getTime() - start.getTime()) / 60000
  const isShort = durationMin <= 30

  return (
    <button
      onClick={onClick}
      title={`${appt.client_name} · ${appt.service_name} · ${formatTime(start)}–${formatTime(end)}`}
      className={`
        absolute left-0.5 right-0.5 rounded-md px-2 text-left
        transition-all duration-150 hover:brightness-95 hover:z-20
        focus:outline-none focus:ring-2 focus:ring-offset-1
        ${STATUS_STYLES[appt.status] ?? "border-l-4"}
        overflow-hidden group z-10
      `}
      style={{
        top: `${top}%`,
        height: `${height}%`,
        backgroundColor: `${color}18`,
        borderLeftColor: color,
        borderTopWidth: 0,
        borderRightWidth: 0,
        borderBottomWidth: 0,
      }}
    >
      <p
        className="font-semibold leading-tight truncate"
        style={{ fontSize: 11, color }}
      >
        {appt.client_name}
      </p>
      {!isShort && (
        <p
          className="truncate leading-tight opacity-80"
          style={{ fontSize: 10, color }}
        >
          {appt.service_name}
        </p>
      )}
      {!isShort && (
        <p
          className="leading-tight opacity-60"
          style={{ fontSize: 10, color }}
        >
          {formatTime(start)}–{formatTime(end)}
        </p>
      )}
    </button>
  )
}

// ─── Coluna de horários ───────────────────────────────────────────────────────

function TimeGutter() {
  return (
    <div
      className="flex-shrink-0 select-none"
      style={{ width: 52 }}
    >
      <div style={{ height: 48 }} />  {/* header spacer */}
      <div
        className="relative"
        style={{ height: HOUR_HEIGHT * TOTAL_HOURS }}
      >
        {Array.from({ length: TOTAL_HOURS + 1 }, (_, i) => (
          <div
            key={i}
            className="absolute right-2 text-xs text-gray-400 dark:text-gray-500 leading-none"
            style={{ top: i * HOUR_HEIGHT - 7, width: 40, textAlign: "right" }}
          >
            {i < TOTAL_HOURS + 1 ? formatHour(START_HOUR + i) : ""}
          </div>
        ))}
      </div>
    </div>
  )
}

// ─── Linha de hora atual ──────────────────────────────────────────────────────

function NowLine() {
  const [now, setNow] = useState(new Date())

  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60000)
    return () => clearInterval(t)
  }, [])

  const top = topOffsetPct(now)
  if (now.getHours() < START_HOUR || now.getHours() >= END_HOUR) return null

  return (
    <div
      className="absolute left-0 right-0 z-30 pointer-events-none"
      style={{ top: `${top}%` }}
    >
      <div className="relative flex items-center">
        <div className="w-2 h-2 rounded-full bg-red-500 -ml-1 flex-shrink-0" />
        <div className="flex-1 h-px bg-red-500" />
      </div>
    </div>
  )
}

// ─── Grade de horas (background) ─────────────────────────────────────────────

function HourGrid() {
  return (
    <div
      className="absolute inset-0 pointer-events-none"
      style={{ height: HOUR_HEIGHT * TOTAL_HOURS }}
    >
      {Array.from({ length: TOTAL_HOURS }, (_, i) => (
        <div
          key={i}
          className="absolute left-0 right-0 border-t border-gray-100 dark:border-gray-800"
          style={{ top: i * HOUR_HEIGHT }}
        />
      ))}
      {Array.from({ length: TOTAL_HOURS }, (_, i) => (
        <div
          key={`half-${i}`}
          className="absolute left-0 right-0 border-t border-dashed border-gray-100 dark:border-gray-800 opacity-60"
          style={{ top: i * HOUR_HEIGHT + HOUR_HEIGHT / 2 }}
        />
      ))}
    </div>
  )
}

// ─── Visualização Semanal ─────────────────────────────────────────────────────

function WeekView({
  weekStart,
  appointments,
  onAppointmentClick,
  onSlotClick,
}: {
  weekStart: Date
  appointments: Appointment[]
  onAppointmentClick: (a: Appointment) => void
  onSlotClick: (date: Date) => void
}) {
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const today = new Date()

  return (
    <div className="flex overflow-x-auto">
      <TimeGutter />

      <div className="flex flex-1 min-w-0">
        {days.map((day) => {
          const dayAppts = appointments.filter((a) =>
            isSameDay(new Date(a.start_at), day)
          )
          const isToday = isSameDay(day, today)

          return (
            <div key={day.toISOString()} className="flex-1 min-w-0 border-l border-gray-100 dark:border-gray-800">
              {/* Cabeçalho do dia */}
              <div
                className={`
                  h-12 flex flex-col items-center justify-center gap-0.5 sticky top-0 z-20
                  bg-white dark:bg-gray-950 border-b border-gray-100 dark:border-gray-800
                `}
              >
                <span className="text-xs font-medium text-gray-400 dark:text-gray-500 uppercase tracking-wide">
                  {DAYS_PT[day.getDay()]}
                </span>
                <span
                  className={`
                    text-sm font-semibold leading-none w-7 h-7 flex items-center justify-center rounded-full
                    ${isToday
                      ? "bg-violet-600 text-white"
                      : "text-gray-700 dark:text-gray-300"
                    }
                  `}
                >
                  {day.getDate()}
                </span>
              </div>

              {/* Coluna de eventos */}
              <div
                className="relative cursor-pointer"
                style={{ height: HOUR_HEIGHT * TOTAL_HOURS }}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  const y = e.clientY - rect.top
                  const mins = Math.floor((y / (HOUR_HEIGHT * TOTAL_HOURS)) * TOTAL_HOURS * 60)
                  const clickedDate = new Date(day)
                  clickedDate.setHours(
                    START_HOUR + Math.floor(mins / 60),
                    Math.floor(mins / 60) * 60 === mins ? 0 : 30,
                    0, 0
                  )
                  onSlotClick(clickedDate)
                }}
              >
                <HourGrid />
                <NowLine />
                {dayAppts.map((a) => (
                  <ApptBlock
                    key={a.id}
                    appt={a}
                    color={a.professional_color}
                    onClick={(e?: React.MouseEvent) => {
                      e?.stopPropagation()
                      onAppointmentClick(a)
                    }}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Visualização Diária ──────────────────────────────────────────────────────

function DayView({
  day,
  appointments,
  professionals,
  onAppointmentClick,
  onSlotClick,
}: {
  day: Date
  appointments: Appointment[]
  professionals: { id: string; name: string; color: string }[]
  onAppointmentClick: (a: Appointment) => void
  onSlotClick: (date: Date, professionalId: string) => void
}) {
  const dayAppts = appointments.filter((a) =>
    isSameDay(new Date(a.start_at), day)
  )

  return (
    <div className="flex overflow-x-auto">
      <TimeGutter />

      <div className="flex flex-1 min-w-0">
        {professionals.map((prof) => {
          const profAppts = dayAppts.filter(
            (a) => a.professional_name === prof.name
          )

          return (
            <div key={prof.id} className="flex-1 min-w-0 border-l border-gray-100 dark:border-gray-800">
              {/* Cabeçalho do profissional */}
              <div
                className="h-12 flex items-center justify-center gap-2 sticky top-0 z-20
                  bg-white dark:bg-gray-950 border-b border-gray-100 dark:border-gray-800 px-2"
              >
                <div
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: prof.color }}
                />
                <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 truncate">
                  {prof.name}
                </span>
              </div>

              {/* Coluna */}
              <div
                className="relative cursor-pointer"
                style={{ height: HOUR_HEIGHT * TOTAL_HOURS }}
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  const y = e.clientY - rect.top
                  const mins = Math.floor((y / (HOUR_HEIGHT * TOTAL_HOURS)) * TOTAL_HOURS * 60)
                  const clickedDate = new Date(day)
                  clickedDate.setHours(
                    START_HOUR + Math.floor(mins / 60),
                    Math.floor(mins / 60) * 60 === mins ? 0 : 30,
                    0, 0
                  )
                  onSlotClick(clickedDate, prof.id)
                }}
              >
                <HourGrid />
                <NowLine />
                {profAppts.map((a) => (
                  <ApptBlock
                    key={a.id}
                    appt={a}
                    color={prof.color}
                    onClick={(e?: React.MouseEvent) => {
                      e?.stopPropagation()
                      onAppointmentClick(a)
                    }}
                  />
                ))}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ─── Mini calendário ──────────────────────────────────────────────────────────

function MiniCalendar({
  selected,
  onChange,
  appointments,
}: {
  selected: Date
  onChange: (d: Date) => void
  appointments: Appointment[]
}) {
  const [viewing, setViewing] = useState(
    new Date(selected.getFullYear(), selected.getMonth(), 1)
  )
  const today = new Date()

  const firstDay = new Date(viewing.getFullYear(), viewing.getMonth(), 1).getDay()
  const daysInMonth = new Date(viewing.getFullYear(), viewing.getMonth() + 1, 0).getDate()

  const hasAppt = (d: Date) =>
    appointments.some((a) => isSameDay(new Date(a.start_at), d))

  return (
    <div className="w-56 flex-shrink-0 select-none">
      {/* Navegação do mês */}
      <div className="flex items-center justify-between mb-2 px-1">
        <button
          onClick={() => setViewing(new Date(viewing.getFullYear(), viewing.getMonth() - 1, 1))}
          className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
        >
          ‹
        </button>
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300 capitalize">
          {MONTHS_PT[viewing.getMonth()]} {viewing.getFullYear()}
        </span>
        <button
          onClick={() => setViewing(new Date(viewing.getFullYear(), viewing.getMonth() + 1, 1))}
          className="w-6 h-6 flex items-center justify-center rounded hover:bg-gray-100 dark:hover:bg-gray-800 text-gray-500"
        >
          ›
        </button>
      </div>

      {/* Dias da semana */}
      <div className="grid grid-cols-7 mb-1">
        {DAYS_PT.map((d) => (
          <div key={d} className="text-center text-xs text-gray-400 font-medium py-0.5">
            {d[0]}
          </div>
        ))}
      </div>

      {/* Grade de dias */}
      <div className="grid grid-cols-7 gap-y-0.5">
        {Array.from({ length: firstDay }, (_, i) => (
          <div key={`empty-${i}`} />
        ))}
        {Array.from({ length: daysInMonth }, (_, i) => {
          const d = new Date(viewing.getFullYear(), viewing.getMonth(), i + 1)
          const isSelected = isSameDay(d, selected)
          const isToday = isSameDay(d, today)
          const dot = hasAppt(d)

          return (
            <button
              key={i}
              onClick={() => onChange(d)}
              className={`
                relative w-7 h-7 mx-auto flex items-center justify-center rounded-full text-xs
                transition-colors duration-100
                ${isSelected
                  ? "bg-violet-600 text-white font-semibold"
                  : isToday
                    ? "border border-violet-400 text-violet-600 dark:text-violet-400 font-semibold"
                    : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
                }
              `}
            >
              {i + 1}
              {dot && !isSelected && (
                <span className="absolute bottom-0.5 left-1/2 -translate-x-1/2 w-1 h-1 rounded-full bg-violet-400" />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

// ─── Modal de detalhes ────────────────────────────────────────────────────────

function ApptModal({
  appt,
  onClose,
}: {
  appt: Appointment
  onClose: () => void
}) {
  const start = new Date(appt.start_at)
  const end   = new Date(appt.end_at)
  const durationMin = Math.round((end.getTime() - start.getTime()) / 60000)

  const statusLabel: Record<string, string> = {
    SCHEDULED:  "Agendado",
    COMPLETED:  "Concluído",
    CANCELLED:  "Cancelado",
    NO_SHOW:    "Não compareceu",
  }

  const statusColor: Record<string, string> = {
    SCHEDULED:  "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
    COMPLETED:  "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
    CANCELLED:  "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
    NO_SHOW:    "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={onClose}
    >
      <div
        className="bg-white dark:bg-gray-900 rounded-2xl shadow-xl w-full max-w-sm p-6 relative"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Cor do profissional */}
        <div
          className="w-1 absolute left-0 top-6 bottom-6 rounded-full"
          style={{ backgroundColor: appt.professional_color }}
        />

        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 text-lg leading-none"
        >
          ×
        </button>

        <div className="pl-3">
          <p className="font-semibold text-gray-900 dark:text-gray-100 text-base leading-snug">
            {appt.client_name}
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {appt.service_name}
          </p>

          <span className={`inline-block mt-3 text-xs font-medium px-2 py-0.5 rounded-full ${statusColor[appt.status]}`}>
            {statusLabel[appt.status]}
          </span>

          <div className="mt-4 space-y-2 text-sm text-gray-600 dark:text-gray-400">
            <div className="flex items-center gap-2">
              <span className="text-base">🕐</span>
              <span>
                {formatTime(start)} – {formatTime(end)}
                <span className="ml-1 text-gray-400">({durationMin} min)</span>
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base">👤</span>
              <span>{appt.professional_name}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-base">📅</span>
              <span>
                {start.getDate()} de {MONTHS_PT[start.getMonth()]} de {start.getFullYear()}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function AgendaCalendar({
  appointments,
  professionals,
  onAppointmentClick,
  onSlotClick,
}: AgendaCalendarProps) {
  type ViewMode = "week" | "day"

  const [view, setView]         = useState<ViewMode>("week")
  const [currentDate, setCurrentDate] = useState(() => {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return d
  })
  const [selectedAppt, setSelectedAppt] = useState<Appointment | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  // Scroll para hora atual ao montar
  useEffect(() => {
    if (!scrollRef.current) return
    const now = new Date()
    const offset = Math.max(0, (now.getHours() - START_HOUR - 1) * HOUR_HEIGHT + 48)
    scrollRef.current.scrollTop = offset
  }, [])

  const weekStart = useMemo(() => startOfWeek(currentDate), [currentDate])

  function prevPeriod() {
    if (view === "week") setCurrentDate(addDays(currentDate, -7))
    else setCurrentDate(addDays(currentDate, -1))
  }

  function nextPeriod() {
    if (view === "week") setCurrentDate(addDays(currentDate, 7))
    else setCurrentDate(addDays(currentDate, 1))
  }

  function goToday() {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    setCurrentDate(d)
  }

  const headerLabel = useMemo(() => {
    if (view === "day") {
      return `${DAYS_PT[currentDate.getDay()]}, ${currentDate.getDate()} de ${MONTHS_PT[currentDate.getMonth()]} de ${currentDate.getFullYear()}`
    }
    const wEnd = addDays(weekStart, 6)
    if (weekStart.getMonth() === wEnd.getMonth()) {
      return `${weekStart.getDate()}–${wEnd.getDate()} de ${MONTHS_PT[weekStart.getMonth()]} de ${weekStart.getFullYear()}`
    }
    return `${weekStart.getDate()} ${MONTHS_PT[weekStart.getMonth()]} – ${wEnd.getDate()} ${MONTHS_PT[wEnd.getMonth()]} ${wEnd.getFullYear()}`
  }, [view, currentDate, weekStart])

  function handleApptClick(a: Appointment) {
    setSelectedAppt(a)
    onAppointmentClick?.(a)
  }

  return (
    <div className="flex flex-col h-full bg-white dark:bg-gray-950 rounded-2xl border border-gray-200 dark:border-gray-800 overflow-hidden">

      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100 dark:border-gray-800 flex-shrink-0">
        {/* Hoje */}
        <button
          onClick={goToday}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg border border-gray-200 dark:border-gray-700
            text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800 transition-colors"
        >
          Hoje
        </button>

        {/* Prev / Next */}
        <div className="flex gap-1">
          {["‹", "›"].map((arrow, i) => (
            <button
              key={arrow}
              onClick={i === 0 ? prevPeriod : nextPeriod}
              className="w-7 h-7 flex items-center justify-center rounded-lg text-gray-500
                hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors text-base leading-none"
            >
              {arrow}
            </button>
          ))}
        </div>

        {/* Título do período */}
        <h2 className="flex-1 text-sm font-semibold text-gray-800 dark:text-gray-200 capitalize">
          {headerLabel}
        </h2>

        {/* Toggle semana / dia */}
        <div className="flex rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          {(["week", "day"] as ViewMode[]).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={`
                px-3 py-1.5 text-xs font-semibold transition-colors
                ${view === v
                  ? "bg-violet-600 text-white"
                  : "text-gray-600 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-800"
                }
              `}
            >
              {v === "week" ? "Semana" : "Dia"}
            </button>
          ))}
        </div>
      </div>

      {/* ── Corpo ────────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* Mini calendário lateral */}
        <div className="hidden lg:flex flex-col gap-6 px-4 py-4 border-r border-gray-100 dark:border-gray-800 flex-shrink-0">
          <MiniCalendar
            selected={currentDate}
            onChange={(d) => setCurrentDate(d)}
            appointments={appointments}
          />

          {/* Legenda de profissionais */}
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">
              Profissionais
            </p>
            {professionals.map((p) => (
              <div key={p.id} className="flex items-center gap-2">
                <div
                  className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: p.color }}
                />
                <span className="text-xs text-gray-600 dark:text-gray-400 truncate">
                  {p.name}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Grade principal com scroll */}
        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto overflow-x-auto"
        >
          {view === "week" ? (
            <WeekView
              weekStart={weekStart}
              appointments={appointments}
              onAppointmentClick={handleApptClick}
              onSlotClick={(date) => onSlotClick?.(date)}
            />
          ) : (
            <DayView
              day={currentDate}
              appointments={appointments}
              professionals={professionals}
              onAppointmentClick={handleApptClick}
              onSlotClick={(date, profId) => onSlotClick?.(date, profId)}
            />
          )}
        </div>
      </div>

      {/* Modal de detalhes */}
      {selectedAppt && (
        <ApptModal
          appt={selectedAppt}
          onClose={() => setSelectedAppt(null)}
        />
      )}
    </div>
  )
}