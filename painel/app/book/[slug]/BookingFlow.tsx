"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { formatBRL } from "@/lib/utils"

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface ServiceOpt {
  id: string
  name: string
  price: string
  duration_minutes: number
  row_key: string
}

interface ProfOpt {
  id: string | null
  name: string
  row_key: string
}

interface DateOpt {
  date: string
  label: string
  has_availability: boolean
  row_key: string
}

interface SlotOpt {
  start_at: string
  end_at: string
  start_display: string
  professional_id: string
  professional_name: string
  row_key: string
}

interface ShiftOpt {
  shift: string           // "manha" | "tarde" | "noite"
  label: string           // "🌅 Manhã (até 12h)"
  slot_count: number
  has_availability: boolean
  row_key: string         // "turno_manha" | "turno_tarde" | "turno_noite"
}

type SrvState =
  | "IDLE"
  | "AWAITING_SERVICE"
  | "AWAITING_PROFESSIONAL"
  | "AWAITING_DATE"
  | "AWAITING_SHIFT"
  | "AWAITING_TIME"
  | "AWAITING_CUSTOMER"
  | "AWAITING_CONFIRMATION"
  | "CONFIRMED"
  | "CANCELLED"

interface ContextSummary {
  customer_name?: string | null
  service_name?: string | null
  service_price?: string | null
  service_duration_minutes?: number | null
  professional_name?: string | null
  selected_date?: string | null
  slot_start_at?: string | null
  slot_end_at?: string | null
  slot_start_display?: string | null
}

interface ConfirmData {
  appointment_id: string
  service_name: string
  professional_name: string
  start_at: string
  start_display: string
  end_at: string
  total_amount: string
}

export interface Session {
  session_id: string
  token: string
  state: SrvState
  options: (ServiceOpt | ProfOpt | DateOpt | SlotOpt | ShiftOpt)[]
  context_summary: ContextSummary
  confirmation: ConfirmData | null
  expires_at: string
  company_timezone: string
  error?: string | null
  dates_has_next?: boolean
  dates_has_previous?: boolean
}

// ─── API ──────────────────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL!

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw Object.assign(new Error(body.detail ?? "Erro desconhecido"), { status: res.status })
  }
  return res.json()
}

// ─── Componentes visuais ──────────────────────────────────────────────────────

function StepHeader({ title, subtitle, onBack }: {
  title: string; subtitle?: string; onBack?: () => void
}) {
  return (
    <div className="mb-6">
      {onBack && (
        <button onClick={onBack} className="text-sm mb-3 flex items-center gap-1 transition-colors"
          style={{ color: "var(--book-primary)" }}>
          ← Voltar
        </button>
      )}
      <h2 className="text-xl font-bold" style={{ color: "var(--book-text)" }}>{title}</h2>
      {subtitle && <p className="text-sm mt-1" style={{ color: "var(--book-text-secondary)" }}>{subtitle}</p>}
    </div>
  )
}

function BookCard({ children, onClick, disabled }: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean
}) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="w-full text-left rounded-xl p-4 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ background: "var(--book-card)", border: "1px solid var(--book-border)" }}
      onMouseEnter={(e) => { if (!disabled) (e.currentTarget as HTMLElement).style.borderColor = "var(--book-primary)" }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--book-border)" }}
    >
      {children}
    </button>
  )
}

function Spinner() {
  return <p className="text-sm py-6 text-center" style={{ color: "var(--book-text-muted)" }}>Carregando…</p>
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div className="rounded-lg p-3 text-sm mb-4" style={{
      background: "color-mix(in srgb, #ef4444 10%, var(--book-card))",
      border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
      color: "#fca5a5",
    }}>{msg}</div>
  )
}

function InputField({ label, type, value, onChange, placeholder, minLength, required }: {
  label: string; type: string; value: string; onChange: (v: string) => void
  placeholder?: string; minLength?: number; required?: boolean
}) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1.5" style={{ color: "var(--book-text-secondary)" }}>
        {label}
      </label>
      <input type={type} value={value} onChange={(e) => onChange(e.target.value)}
        required={required} minLength={minLength} placeholder={placeholder}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-all"
        style={{ background: "var(--book-card)", border: "1px solid var(--book-border)", color: "var(--book-text)" }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = "var(--book-primary)"
          e.currentTarget.style.boxShadow = "0 0 0 2px color-mix(in srgb, var(--book-primary) 20%, transparent)"
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = "var(--book-border)"
          e.currentTarget.style.boxShadow = "none"
        }}
      />
    </div>
  )
}

// ─── Componente principal do fluxo ────────────────────────────────────────────
// Recebe slug e companyName como props — não busca /info internamente,
// pois a landing page já carregou essas informações.

export default function BookingFlow({
  slug,
  companyName,
  initialToken,
  onTokenChange,
}: {
  slug: string
  companyName: string
  initialToken?: string | null
  onTokenChange?: (token: string) => void
}) {
  const router = useRouter()

  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  const [custName,  setCustName]  = useState("")
  const [custPhone, setCustPhone] = useState("")

  // ── Iniciar ou retomar sessão ─────────────────────────────────────────────
  useEffect(() => {
    if (initialToken) {
      apiFetch<Session>(`/booking/${slug}/session/${initialToken}`)
        .then(setSession)
        .catch((e: { status?: number; message: string }) => {
          if (e.status !== 410) console.warn("Falha ao retomar sessão:", e.message)
          startNewSession()
        })
    } else {
      startNewSession()
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function startNewSession() {
    setLoading(true)
    setError(null)
    try {
      const result = await apiFetch<Session>(`/booking/${slug}/start`, {
        method: "POST",
        body: JSON.stringify({}),
      })
      setSession(result)
      onTokenChange?.(result.token)
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // ── Dispatch ──────────────────────────────────────────────────────────────
  const dispatch = useCallback(
    async (action: string, payload: Record<string, unknown> = {}) => {
      if (!session) return
      setError(null)
      setLoading(true)
      try {
        const result = await apiFetch<Partial<Session>>(`/booking/${slug}/update`, {
          method: "POST",
          body: JSON.stringify({ session_id: session.session_id, action, payload }),
        })
        setSession((prev) => prev ? { ...prev, ...result } : null)
        if (result.error === "SLOT_UNAVAILABLE") {
          setError("Este horário acabou de ser ocupado. Escolha outro.")
        }
      } catch (e: unknown) {
        setError((e as Error).message)
      } finally {
        setLoading(false)
      }
    },
    [session, slug],
  )

  const handleBack  = () => dispatch("BACK")
  const handleReset = () => dispatch("RESET")

  // ── Barra de progresso ────────────────────────────────────────────────────
  const PROGRESS_STEPS: SrvState[] = [
    "AWAITING_SERVICE", "AWAITING_PROFESSIONAL", "AWAITING_DATE",
    "AWAITING_SHIFT", "AWAITING_TIME", "AWAITING_CUSTOMER", "AWAITING_CONFIRMATION",
  ]
  const currentIdx  = session ? PROGRESS_STEPS.indexOf(session.state) : -1
  const showProgress = session && !["IDLE", "CONFIRMED", "CANCELLED"].includes(session.state)

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="book-page">

      {/* Barra de progresso */}
      {showProgress && (
        <div className="max-w-lg mx-auto px-6 pt-2 pb-4">
          <div className="flex gap-1">
            {PROGRESS_STEPS.map((s, i) => (
              <div key={s} className="h-0.5 flex-1 rounded-full transition-colors duration-300"
                style={{ background: currentIdx >= i ? "var(--book-gradient-gold)" : "var(--book-border)" }} />
            ))}
          </div>
        </div>
      )}

      <div className="max-w-lg mx-auto px-6 py-4">

        {/* Erro de inicialização */}
        {!session && error && (
          <div className="text-center py-8">
            <ErrorBanner msg={error} />
            <button onClick={startNewSession} className="book-btn-primary px-6 py-3 text-sm mt-4">
              Tentar novamente
            </button>
          </div>
        )}

        {!session && loading && <Spinner />}

        {session?.state === "AWAITING_SERVICE" && (
          <ServiceStep options={session.options as ServiceOpt[]} loading={loading}
            onSelect={(opt) => dispatch("SELECT_SERVICE", { service_id: opt.id })} />
        )}

        {session?.state === "AWAITING_PROFESSIONAL" && (
          <ProfessionalStep options={session.options as ProfOpt[]} summary={session.context_summary}
            loading={loading} onBack={handleBack}
            onSelect={(opt) => dispatch("SELECT_PROFESSIONAL", { professional_id: opt.id ?? "any" })} />
        )}

        {session?.state === "AWAITING_DATE" && (
          <DateStep
            options={session.options as DateOpt[]}
            summary={session.context_summary}
            hasNext={session.dates_has_next ?? false}
            hasPrevious={session.dates_has_previous ?? false}
            loading={loading}
            onBack={handleBack}
            onSelect={(opt) => dispatch("SELECT_DATE", { date: opt.date, row_key: opt.row_key })}
            onNavigate={(offsetDays) => dispatch("NAVIGATE_DATES", { offset_days: offsetDays })}
          />
        )}

        {session?.state === "AWAITING_SHIFT" && (
          <ShiftStep
            options={session.options as ShiftOpt[]}
            summary={session.context_summary}
            loading={loading}
            onBack={handleBack}
            onSelect={(opt) => dispatch("SELECT_SHIFT", { shift: opt.shift, row_key: opt.row_key })}
          />
        )}

        {session?.state === "AWAITING_TIME" && (
          <TimeStep options={session.options as SlotOpt[]} summary={session.context_summary}
            companyTimezone={session.company_timezone}
            loading={loading} error={error} onBack={handleBack}
            onSelect={(opt) => dispatch("SELECT_TIME", {
              start_at: opt.start_at, end_at: opt.end_at,
              professional_id: opt.professional_id, row_key: opt.row_key,
            })} />
        )}

        {session?.state === "AWAITING_CUSTOMER" && (
          <CustomerForm name={custName} phone={custPhone}
            onName={setCustName} onPhone={setCustPhone}
            loading={loading} error={error} onBack={handleBack}
            companyName={companyName}
            onSubmit={(e) => {
              e.preventDefault()
              dispatch("SET_CUSTOMER", { name: custName, phone: custPhone })
            }} />
        )}

        {session?.state === "AWAITING_CONFIRMATION" && (
          <ConfirmStep summary={session.context_summary} loading={loading}
            companyTimezone={session.company_timezone}
            error={error} onBack={handleBack}
            onConfirm={() => dispatch("CONFIRM")} />
        )}

        {session?.state === "CONFIRMED" && session.confirmation && (
          <ConfirmedView confirmation={session.confirmation}
            companyTimezone={session.company_timezone}
            token={session.token} onReset={handleReset} />
        )}

        {session?.state === "CANCELLED" && (
          <CancelledView onReset={handleReset} />
        )}

      </div>
    </div>
  )
}

// ─── Etapas (idênticas ao original) ──────────────────────────────────────────

function ServiceStep({ options, loading, onSelect }: {
  options: ServiceOpt[]; loading: boolean; onSelect: (opt: ServiceOpt) => void
}) {
  return (
    <div>
      <StepHeader title="Qual serviço você quer agendar?" />
      {loading ? <Spinner /> : (
        <div className="space-y-3">
          {options.map((svc) => (
            <BookCard key={svc.row_key} onClick={() => onSelect(svc)} disabled={loading}>
              <div className="flex gap-4 items-center">
                <div className="h-12 w-12 rounded-lg flex items-center justify-center text-xl shrink-0"
                  style={{ background: "var(--book-black-600)", border: "1px solid var(--book-border)" }}>
                  ✂️
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold" style={{ color: "var(--book-text)" }}>{svc.name}</div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--book-text-muted)" }}>{svc.duration_minutes} min</div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-semibold" style={{ color: "var(--book-primary)" }}>
                    {formatBRL(svc.price)}
                  </div>
                </div>
              </div>
            </BookCard>
          ))}
          {options.length === 0 && (
            <p className="text-sm text-center py-8" style={{ color: "var(--book-text-muted)" }}>
              Nenhum serviço disponível no momento.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ProfessionalStep({ options, summary, loading, onBack, onSelect }: {
  options: ProfOpt[]; summary: ContextSummary; loading: boolean
  onBack: () => void; onSelect: (opt: ProfOpt) => void
}) {
  return (
    <div>
      <StepHeader title="Com quem você prefere?" subtitle={summary.service_name ?? undefined} onBack={onBack} />
      {loading ? <Spinner /> : (
        <div className="space-y-3">
          {options.map((prof, i) => (
            <BookCard key={prof.row_key ?? `p-${i}`} onClick={() => onSelect(prof)} disabled={loading}>
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-full flex items-center justify-center font-bold text-sm shrink-0"
                  style={{ background: "var(--book-black-600)", border: "1px solid var(--book-border)", color: "var(--book-primary)" }}>
                  {prof.name[0]}
                </div>
                <span className="font-medium" style={{ color: "var(--book-text)" }}>{prof.name}</span>
              </div>
            </BookCard>
          ))}
        </div>
      )}
    </div>
  )
}

function DateStep({ options, summary, hasNext, hasPrevious, loading, onBack, onSelect, onNavigate }: {
  options: DateOpt[]
  summary: ContextSummary
  hasNext: boolean
  hasPrevious: boolean
  loading: boolean
  onBack: () => void
  onSelect: (opt: DateOpt) => void
  onNavigate: (offsetDays: number) => void
}) {
  const [offsetDays, setOffsetDays] = useState(0)

  const subtitle   = [summary.service_name, summary.professional_name].filter(Boolean).join(" · ")
  const available  = options.filter((d) => d.has_availability)
  const hiddenCount = options.length - available.length

  function handleNext() {
    const next = offsetDays + 7
    setOffsetDays(next)
    onNavigate(next)
  }

  function handlePrev() {
    const prev = Math.max(0, offsetDays - 7)
    setOffsetDays(prev)
    onNavigate(prev)
  }

  return (
    <div>
      <StepHeader title="Qual dia funciona para você?" subtitle={subtitle || undefined} onBack={onBack} />

      {loading ? <Spinner /> : (
        <>
          {/* Botão "dias anteriores" */}
          {hasPrevious && (
            <button onClick={handlePrev} disabled={loading}
              className="w-full text-sm mb-3 flex items-center gap-1 disabled:opacity-40"
              style={{ color: "var(--book-primary)" }}>
              ← 7 dias anteriores
            </button>
          )}

          <div className="space-y-2">
            {available.length === 0 ? (
              <p className="text-sm py-6 text-center" style={{ color: "var(--book-text-muted)" }}>
                Nenhum dia disponível nesta semana.
              </p>
            ) : (
              <>
                {available.map((d) => (
                  <button key={d.row_key} onClick={() => onSelect(d)} disabled={loading}
                    className="w-full text-left rounded-xl px-4 py-3 transition-all duration-150 disabled:opacity-40"
                    style={{ background: "var(--book-card)", border: "1px solid var(--book-border)" }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--book-primary)" }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = "var(--book-border)" }}>
                    <span className="font-medium" style={{ color: "var(--book-text)" }}>{d.label}</span>
                  </button>
                ))}
                {hiddenCount > 0 && (
                  <p className="text-xs pt-1" style={{ color: "var(--book-text-muted)" }}>
                    {hiddenCount} dia{hiddenCount > 1 ? "s" : ""} sem disponibilidade neste período.
                  </p>
                )}
              </>
            )}
          </div>

          {/* Botão "próximos 7 dias" */}
          {hasNext && (
            <button onClick={handleNext} disabled={loading}
              className="w-full text-sm mt-3 flex items-center justify-end gap-1 disabled:opacity-40"
              style={{ color: "var(--book-primary)" }}>
              Ver próximos 7 dias →
            </button>
          )}
        </>
      )}
    </div>
  )
}

function ShiftStep({ options, summary, loading, onBack, onSelect }: {
  options: ShiftOpt[]
  summary: ContextSummary
  loading: boolean
  onBack: () => void
  onSelect: (opt: ShiftOpt) => void
}) {
  const dateLabel = summary.selected_date
    ? new Date(summary.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
        weekday: "long", day: "2-digit", month: "long",
      })
    : undefined

  return (
    <div>
      <StepHeader title="Qual período prefere?" subtitle={dateLabel} onBack={onBack} />
      {loading ? <Spinner /> : (
        <div className="space-y-3">
          {options.map((shift) => {
            const unavailable = !shift.has_availability
            return (
              <button
                key={shift.row_key}
                onClick={() => !unavailable && onSelect(shift)}
                disabled={loading || unavailable}
                className="w-full text-left rounded-xl p-4 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
                style={{ background: "var(--book-card)", border: "1px solid var(--book-border)" }}
                onMouseEnter={(e) => {
                  if (!unavailable) (e.currentTarget as HTMLElement).style.borderColor = "var(--book-primary)"
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.borderColor = "var(--book-border)"
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium" style={{ color: unavailable ? "var(--book-text-muted)" : "var(--book-text)" }}>
                    {shift.label}
                  </span>
                  {unavailable ? (
                    <span className="text-xs" style={{ color: "var(--book-text-muted)" }}>
                      indisponível
                    </span>
                  ) : (
                    <span className="text-xs font-medium" style={{ color: "var(--book-primary)" }}>
                      {shift.slot_count} horário{shift.slot_count !== 1 ? "s" : ""}
                    </span>
                  )}
                </div>
              </button>
            )
          })}
          {options.every((s) => !s.has_availability) && (
            <p className="text-sm text-center pt-4" style={{ color: "var(--book-text-muted)" }}>
              Nenhum horário disponível neste dia.{" "}
              <button onClick={onBack} className="underline" style={{ color: "var(--book-primary)" }}>
                Escolher outra data
              </button>
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function TimeStep({ options, summary, companyTimezone, loading, error, onBack, onSelect }: {
  options: SlotOpt[]; summary: ContextSummary; companyTimezone: string; loading: boolean
  error: string | null; onBack: () => void; onSelect: (opt: SlotOpt) => void
}) {
  const dateLabel = summary.selected_date
    ? new Date(summary.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
        weekday: "long", day: "2-digit", month: "long", timeZone: companyTimezone,
      })
    : undefined

  return (
    <div>
      {/* onBack aqui vai para AWAITING_SHIFT (alterar turno) */}
      <StepHeader title="Escolha um horário" subtitle={dateLabel} onBack={onBack} />
      {error && <ErrorBanner msg={error} />}
      {loading ? <Spinner /> : options.length === 0 ? (
        <div className="text-center py-8">
          <p className="mb-4" style={{ color: "var(--book-text-secondary)" }}>Nenhum horário disponível neste dia.</p>
          <button onClick={onBack} className="text-sm underline" style={{ color: "var(--book-primary)" }}>
            Escolher outra data
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {options.map((slot) => (
            <button key={slot.row_key} onClick={() => onSelect(slot)} disabled={loading}
              className="rounded-xl py-3 text-sm font-medium transition-all duration-150 disabled:opacity-40"
              style={{ background: "var(--book-card)", border: "1px solid var(--book-border)", color: "var(--book-text)" }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = "var(--book-primary)"
                ;(e.currentTarget as HTMLButtonElement).style.color = "var(--book-primary)"
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor = "var(--book-border)"
                ;(e.currentTarget as HTMLButtonElement).style.color = "var(--book-text)"
              }}>
              {slot.start_display}
              <div className="text-xs truncate px-1 mt-0.5" style={{ color: "var(--book-text-muted)" }}>
                {slot.professional_name}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function CustomerForm({ name, phone, onName, onPhone, loading, error, onBack, onSubmit, companyName }: {
  name: string; phone: string; onName: (v: string) => void; onPhone: (v: string) => void
  loading: boolean; error: string | null; onBack: () => void
  onSubmit: (e: React.FormEvent) => void; companyName: string
}) {
  return (
    <div>
      <StepHeader title="Quase lá! Seus dados"
        subtitle={`Para confirmar seu horário em ${companyName}`} onBack={onBack} />
      <form onSubmit={onSubmit} className="space-y-4">
        <InputField label="Nome completo *" type="text" value={name} onChange={onName}
          placeholder="Seu nome" minLength={2} required />
        <InputField label="WhatsApp / Telefone *" type="tel" value={phone} onChange={onPhone}
          placeholder="(11) 99999-9999" minLength={10} required />
        {error && <ErrorBanner msg={error} />}
        <button type="submit" disabled={loading} className="book-btn-primary w-full py-3 text-sm mt-2">
          {loading ? "Aguarde…" : "Continuar →"}
        </button>
      </form>
    </div>
  )
}

function ConfirmStep({ summary, companyTimezone, loading, error, onBack, onConfirm }: {
  summary: ContextSummary; companyTimezone: string; loading: boolean; error: string | null
  onBack: () => void; onConfirm: () => void
}) {
  return (
    <div>
      <StepHeader title="Confirmar agendamento" onBack={onBack} />
      <div className="rounded-xl p-4 mb-6" style={{
        background: "var(--book-card)", border: "1px solid var(--book-border)",
        borderLeft: "3px solid var(--book-primary)",
      }}>
        <div className="font-semibold mb-3" style={{ color: "var(--book-text)" }}>
          {summary.service_name ?? "Serviço"}
        </div>
        <div className="text-sm space-y-1.5" style={{ color: "var(--book-text-secondary)" }}>
          {summary.customer_name && <div>👤 {summary.customer_name}</div>}
          {summary.professional_name && <div>💈 {summary.professional_name}</div>}
          {summary.selected_date && (
            <div>
              📅{" "}
              {new Date(summary.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
                weekday: "long", day: "2-digit", month: "long", timeZone: companyTimezone,
              })}
              {summary.slot_start_display && ` às ${summary.slot_start_display}`}
            </div>
          )}
          {summary.service_duration_minutes && <div>⏱ {summary.service_duration_minutes} min</div>}
        </div>
        {summary.service_price && (
          <div className="text-sm font-semibold mt-3 pt-3"
            style={{ color: "var(--book-primary)", borderTop: "1px solid var(--book-border)" }}>
            {formatBRL(summary.service_price)}
          </div>
        )}
      </div>
      {error && <ErrorBanner msg={error} />}
      <button onClick={onConfirm} disabled={loading} className="book-btn-primary w-full py-3 text-sm">
        {loading ? "Confirmando…" : "Confirmar agendamento"}
      </button>
    </div>
  )
}

function ConfirmedView({ confirmation, companyTimezone, token, onReset }: {
  confirmation: ConfirmData; companyTimezone: string; token: string; onReset: () => void
}) {
  function fmtDate(iso: string) {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "full", timeStyle: "short", timeZone: companyTimezone,
    })
  }
  return (
    <div className="text-center py-6">
      <div className="w-16 h-16 rounded-full flex items-center justify-center text-2xl mx-auto mb-5"
        style={{ background: "color-mix(in srgb, var(--book-primary) 15%, var(--book-card))", border: "1px solid var(--book-primary)" }}>
        ✓
      </div>
      <h2 className="text-2xl font-bold mb-1" style={{ color: "var(--book-text)" }}>Agendado!</h2>
      <p className="mb-8" style={{ color: "var(--book-text-secondary)" }}>Seu horário está confirmado.</p>
      <div className="rounded-2xl p-6 text-left space-y-3 mb-6"
        style={{ background: "var(--book-card)", border: "1px solid var(--book-border)" }}>
        {[
          { label: "Serviço", value: confirmation.service_name },
          { label: "Profissional", value: confirmation.professional_name },
          { label: "Data e hora", value: fmtDate(confirmation.start_at) },
        ].map(({ label, value }) => (
          <div key={label} className="flex justify-between text-sm">
            <span style={{ color: "var(--book-text-muted)" }}>{label}</span>
            <span className="font-medium text-right" style={{ color: "var(--book-text)" }}>{value}</span>
          </div>
        ))}
        <div className="flex justify-between text-sm pt-3"
          style={{ borderTop: "1px solid color-mix(in srgb, var(--book-primary) 20%, transparent)" }}>
          <span style={{ color: "var(--book-text-muted)" }}>Total</span>
          <span className="font-bold" style={{ color: "var(--book-primary)" }}>{formatBRL(confirmation.total_amount)}</span>
        </div>
      </div>
      <p className="text-xs mb-6" style={{ color: "var(--book-text-muted)" }}>
        Código:{" "}
        <span className="font-mono" style={{ color: "var(--book-text-secondary)" }}>
          {token.slice(0, 8).toUpperCase()}
        </span>
      </p>
      <button onClick={onReset} className="text-sm underline" style={{ color: "var(--book-primary)" }}>
        Fazer outro agendamento
      </button>
    </div>
  )
}

function CancelledView({ onReset }: { onReset: () => void }) {
  return (
    <div className="text-center py-6">
      <div className="text-4xl mb-4">✕</div>
      <h2 className="text-xl font-bold mb-2" style={{ color: "var(--book-text)" }}>Agendamento cancelado</h2>
      <p className="mb-8 text-sm" style={{ color: "var(--book-text-secondary)" }}>
        Seu agendamento foi cancelado com sucesso.
      </p>
      <button onClick={onReset} className="book-btn-primary px-6 py-3 text-sm">
        Fazer novo agendamento
      </button>
    </div>
  )
}