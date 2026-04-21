"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { formatBRL } from "@/lib/utils"

// ─── Tipos de opção (espelham os schemas HTTP do backend) ─────────────────────

interface ServiceOpt {
  id: string
  name: string
  price: string
  duration_minutes: number
  row_key: string
}

interface ProfOpt {
  id: string | null   // null = "Qualquer disponível"
  name: string
  row_key: string
}

interface DateOpt {
  date: string            // "YYYY-MM-DD"
  label: string           // "Hoje (20/04)"
  has_availability: boolean
  row_key: string
}

interface SlotOpt {
  start_at: string        // ISO UTC
  end_at: string          // ISO UTC
  start_display: string   // "14:30" no tz da empresa
  professional_id: string
  professional_name: string
  row_key: string
}

// ─── Estado da sessão FSM ─────────────────────────────────────────────────────

type SrvState =
  | "IDLE"
  | "AWAITING_SERVICE"
  | "AWAITING_PROFESSIONAL"
  | "AWAITING_DATE"
  | "AWAITING_TIME"
  | "AWAITING_CONFIRMATION"
  | "CONFIRMED"
  | "CANCELLED"

interface ContextSummary {
  customer_name?: string | null
  service_name?: string | null
  service_price?: string | null
  service_duration_minutes?: number | null
  professional_name?: string | null
  selected_date?: string | null    // "YYYY-MM-DD"
  slot_start_at?: string | null    // ISO UTC
  slot_end_at?: string | null      // ISO UTC
  slot_start_display?: string | null  // "14:30"
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

interface Session {
  session_id: string
  token: string
  state: SrvState
  options: (ServiceOpt | ProfOpt | DateOpt | SlotOpt)[]
  context_summary: ContextSummary
  confirmation: ConfirmData | null
  expires_at: string
  company_timezone: string
  error?: string | null
}

interface CompanyInfo {
  company_name: string
  active: boolean
  online_booking_enabled: boolean
  booking_url: string
}

// ─── Helpers de API ───────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL!

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const err = Object.assign(new Error(body.detail ?? "Erro desconhecido"), { status: res.status })
    throw err
  }
  return res.json()
}

// ─── Componentes visuais ──────────────────────────────────────────────────────

function StepHeader({
  title,
  subtitle,
  onBack,
}: {
  title: string
  subtitle?: string
  onBack?: () => void
}) {
  return (
    <div className="mb-6">
      {onBack && (
        <button
          onClick={onBack}
          className="text-sm mb-3 flex items-center gap-1 transition-colors"
          style={{ color: "var(--book-primary)" }}
        >
          ← Voltar
        </button>
      )}
      <h2 className="text-xl font-bold" style={{ color: "var(--book-text)" }}>
        {title}
      </h2>
      {subtitle && (
        <p className="text-sm mt-1" style={{ color: "var(--book-text-secondary)" }}>
          {subtitle}
        </p>
      )}
    </div>
  )
}

function BookCard({
  children,
  onClick,
  disabled,
}: {
  children: React.ReactNode
  onClick?: () => void
  disabled?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="w-full text-left rounded-xl p-4 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
      style={{
        background: "var(--book-card)",
        border: "1px solid var(--book-border)",
      }}
      onMouseEnter={(e) => {
        if (!disabled)
          (e.currentTarget as HTMLElement).style.borderColor = "var(--book-primary)"
      }}
      onMouseLeave={(e) => {
        ;(e.currentTarget as HTMLElement).style.borderColor = "var(--book-border)"
      }}
    >
      {children}
    </button>
  )
}

function Spinner() {
  return (
    <p className="text-sm py-6 text-center" style={{ color: "var(--book-text-muted)" }}>
      Carregando…
    </p>
  )
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div
      className="rounded-lg p-3 text-sm mb-4"
      style={{
        background: "color-mix(in srgb, #ef4444 10%, var(--book-card))",
        border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
        color: "#fca5a5",
      }}
    >
      {msg}
    </div>
  )
}

function InputField({
  label,
  type,
  value,
  onChange,
  placeholder,
  minLength,
  required,
}: {
  label: string
  type: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
  minLength?: number
  required?: boolean
}) {
  return (
    <div>
      <label
        className="block text-sm font-medium mb-1.5"
        style={{ color: "var(--book-text-secondary)" }}
      >
        {label}
      </label>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        minLength={minLength}
        placeholder={placeholder}
        className="w-full rounded-lg px-3 py-2.5 text-sm outline-none transition-all"
        style={{
          background: "var(--book-card)",
          border: "1px solid var(--book-border)",
          color: "var(--book-text)",
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = "var(--book-primary)"
          e.currentTarget.style.boxShadow =
            "0 0 0 2px color-mix(in srgb, var(--book-primary) 20%, transparent)"
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = "var(--book-border)"
          e.currentTarget.style.boxShadow = "none"
        }}
      />
    </div>
  )
}

// ─── Componente Principal ─────────────────────────────────────────────────────

export default function BookingPage() {
  const { slug } = useParams<{ slug: string }>()
  const searchParams = useSearchParams()
  const router = useRouter()

  // Info da empresa
  const [company, setCompany] = useState<CompanyInfo | null>(null)
  const [companyError, setCompanyError] = useState<string | null>(null)

  // Sessão FSM
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Formulário de identificação (exibido quando session=null ou state=IDLE)
  const [custName, setCustName] = useState("")
  const [custPhone, setCustPhone] = useState("")

  // ── Carregar info da empresa ─────────────────────────────────────────────────
  useEffect(() => {
    apiFetch<CompanyInfo>(`/booking/${slug}/info`)
      .then(setCompany)
      .catch((e: Error) => setCompanyError(e.message))
  }, [slug])

  // ── Tentar retomar sessão existente pelo token na URL (?t=…) ─────────────────
  useEffect(() => {
    const token = searchParams.get("t")
    if (!token || !company) return

    apiFetch<Session>(`/booking/${slug}/session/${token}`)
      .then(setSession)
      .catch((e: { status?: number; message: string }) => {
        // 410 = expirada → não tratar como erro; usuário verá o formulário normalmente
        if (e.status !== 410) setError(e.message)
        // Limpar token inválido da URL
        const url = new URL(window.location.href)
        url.searchParams.delete("t")
        router.replace(url.pathname + url.search, { scroll: false })
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [company]) // executa uma vez após carregar empresa

  // ── Criar sessão (formulário de identificação) ────────────────────────────────
  async function handleStart(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = await apiFetch<Session>(`/booking/${slug}/start`, {
        method: "POST",
        body: JSON.stringify({
          customer_name: custName.trim(),
          customer_phone: custPhone.trim(),
        }),
      })
      setSession(result)
      // Persistir token na URL para retomada sem reload
      const url = new URL(window.location.href)
      url.searchParams.set("t", result.token)
      router.replace(url.pathname + url.search, { scroll: false })
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // ── Dispatch: aplica qualquer ação FSM ───────────────────────────────────────
  const dispatch = useCallback(
    async (action: string, payload: Record<string, unknown> = {}) => {
      if (!session) return
      setError(null)
      setLoading(true)
      try {
        const result = await apiFetch<Session>(`/booking/${slug}/update`, {
          method: "POST",
          body: JSON.stringify({
            session_id: session.session_id,
            action,
            payload,
          }),
        })
        setSession(result)
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

  // ── Recomeçar do início (mantém sessão e token, vai para AWAITING_SERVICE) ───
  function handleReset() {
    dispatch("RESET")
  }

  // ── BACK ─────────────────────────────────────────────────────────────────────
  function handleBack() {
    dispatch("BACK")
  }

  // ─── Guards de carregamento / erro ────────────────────────────────────────────

  if (companyError) {
    return (
      <div
        className="book-page min-h-screen flex items-center justify-center"
        style={{ background: "var(--book-gradient-dark)" }}
      >
        <div className="text-center max-w-sm px-6">
          <div className="text-4xl mb-4">😕</div>
          <h1 className="text-xl font-bold mb-2" style={{ color: "var(--book-text)" }}>
            Página não encontrada
          </h1>
          <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
            {companyError}
          </p>
        </div>
      </div>
    )
  }

  if (!company) {
    return (
      <div
        className="book-page min-h-screen flex items-center justify-center"
        style={{ background: "var(--book-gradient-dark)" }}
      >
        <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
          Carregando…
        </p>
      </div>
    )
  }

  // ─── Passos da barra de progresso ─────────────────────────────────────────────
  const PROGRESS_STEPS: SrvState[] = [
    "AWAITING_SERVICE",
    "AWAITING_PROFESSIONAL",
    "AWAITING_DATE",
    "AWAITING_TIME",
    "AWAITING_CONFIRMATION",
  ]
  const currentIdx = session ? PROGRESS_STEPS.indexOf(session.state) : -1
  const showProgress =
    session &&
    !["IDLE", "CONFIRMED", "CANCELLED"].includes(session.state)

  // ─── Render ───────────────────────────────────────────────────────────────────
  return (
    <div
      className="book-page min-h-screen"
      style={{ background: "var(--book-gradient-dark)" }}
    >
      {/* ── Header ───────────────────────────────────────────────────────────── */}
      <div
        style={{
          background: "var(--book-surface)",
          borderBottom: "1px solid var(--book-border)",
        }}
      >
        <div className="max-w-lg mx-auto px-6 py-4">
          <h1 className="text-lg font-bold" style={{ color: "var(--book-text)" }}>
            {company.company_name}
          </h1>
          <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
            Agendamento online
          </p>
        </div>
      </div>

      {/* ── Barra de progresso ────────────────────────────────────────────────── */}
      {showProgress && (
        <div className="max-w-lg mx-auto px-6 pt-4">
          <div className="flex gap-1">
            {PROGRESS_STEPS.map((s, i) => (
              <div
                key={s}
                className="h-0.5 flex-1 rounded-full transition-colors duration-300"
                style={{
                  background:
                    currentIdx >= i
                      ? "var(--book-gradient-gold)"
                      : "var(--book-border)",
                }}
              />
            ))}
          </div>
        </div>
      )}

      <div className="max-w-lg mx-auto px-6 py-8">

        {/* ── IDLE / sem sessão: formulário de identificação ────────────────── */}
        {(!session || session.state === "IDLE") && (
          <CustomerForm
            name={custName}
            phone={custPhone}
            onName={setCustName}
            onPhone={setCustPhone}
            loading={loading}
            error={error}
            onSubmit={handleStart}
            companyName={company.company_name}
          />
        )}

        {/* ── AWAITING_SERVICE ──────────────────────────────────────────────── */}
        {session?.state === "AWAITING_SERVICE" && (
          <ServiceStep
            options={session.options as ServiceOpt[]}
            loading={loading}
            onSelect={(opt) =>
              dispatch("SELECT_SERVICE", { service_id: opt.id, row_key: opt.row_key })
            }
          />
        )}

        {/* ── AWAITING_PROFESSIONAL ─────────────────────────────────────────── */}
        {session?.state === "AWAITING_PROFESSIONAL" && (
          <ProfessionalStep
            options={session.options as ProfOpt[]}
            summary={session.context_summary}
            loading={loading}
            onBack={handleBack}
            onSelect={(opt) =>
              dispatch(
                "SELECT_PROFESSIONAL",
                opt.id
                  ? { professional_id: opt.id, row_key: opt.row_key }
                  : { row_key: "prof_any" },
              )
            }
          />
        )}

        {/* ── AWAITING_DATE ─────────────────────────────────────────────────── */}
        {session?.state === "AWAITING_DATE" && (
          <DateStep
            options={session.options as DateOpt[]}
            summary={session.context_summary}
            loading={loading}
            onBack={handleBack}
            onSelect={(opt) =>
              dispatch("SELECT_DATE", { date: opt.date, row_key: opt.row_key })
            }
          />
        )}

        {/* ── AWAITING_TIME ─────────────────────────────────────────────────── */}
        {session?.state === "AWAITING_TIME" && (
          <TimeStep
            options={session.options as SlotOpt[]}
            summary={session.context_summary}
            loading={loading}
            error={error}
            onBack={handleBack}
            onSelect={(opt) =>
              dispatch("SELECT_TIME", {
                start_at: opt.start_at,
                end_at: opt.end_at,
                professional_id: opt.professional_id,
                row_key: opt.row_key,
              })
            }
          />
        )}

        {/* ── AWAITING_CONFIRMATION ─────────────────────────────────────────── */}
        {session?.state === "AWAITING_CONFIRMATION" && (
          <ConfirmStep
            summary={session.context_summary}
            loading={loading}
            error={error}
            onBack={handleBack}
            onConfirm={() => dispatch("CONFIRM")}
          />
        )}

        {/* ── CONFIRMED ─────────────────────────────────────────────────────── */}
        {session?.state === "CONFIRMED" && session.confirmation && (
          <ConfirmedView
            confirmation={session.confirmation}
            token={session.token}
            onReset={handleReset}
          />
        )}

        {/* ── CANCELLED ─────────────────────────────────────────────────────── */}
        {session?.state === "CANCELLED" && (
          <CancelledView onReset={handleReset} />
        )}

      </div>
    </div>
  )
}

// ─── Etapa 0: Identificação do cliente ───────────────────────────────────────

function CustomerForm({
  name,
  phone,
  onName,
  onPhone,
  loading,
  error,
  onSubmit,
  companyName,
}: {
  name: string
  phone: string
  onName: (v: string) => void
  onPhone: (v: string) => void
  loading: boolean
  error: string | null
  onSubmit: (e: React.FormEvent) => void
  companyName: string
}) {
  return (
    <div>
      <StepHeader
        title="Olá! Vamos agendar"
        subtitle={`Informe seus dados para continuar em ${companyName}`}
      />
      <form onSubmit={onSubmit} className="space-y-4">
        <InputField
          label="Nome completo *"
          type="text"
          value={name}
          onChange={onName}
          placeholder="Seu nome"
          minLength={2}
          required
        />
        <InputField
          label="WhatsApp / Telefone *"
          type="tel"
          value={phone}
          onChange={onPhone}
          placeholder="(11) 99999-9999"
          minLength={10}
          required
        />
        {error && <ErrorBanner msg={error} />}
        <button
          type="submit"
          disabled={loading}
          className="book-btn-primary w-full py-3 text-sm mt-2"
        >
          {loading ? "Aguarde…" : "Ver serviços disponíveis →"}
        </button>
      </form>
    </div>
  )
}

// ─── Etapa 1: Serviços ────────────────────────────────────────────────────────

function ServiceStep({
  options,
  loading,
  onSelect,
}: {
  options: ServiceOpt[]
  loading: boolean
  onSelect: (opt: ServiceOpt) => void
}) {
  return (
    <div>
      <StepHeader title="Qual serviço você quer agendar?" />
      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {options.map((svc) => (
            <BookCard key={svc.row_key} onClick={() => onSelect(svc)} disabled={loading}>
              <div className="flex gap-4 items-center">
                <div
                  className="h-12 w-12 rounded-lg flex items-center justify-center text-xl shrink-0"
                  style={{
                    background: "var(--book-black-600)",
                    border: "1px solid var(--book-border)",
                  }}
                >
                  ✂️
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-semibold" style={{ color: "var(--book-text)" }}>
                    {svc.name}
                  </div>
                  <div className="text-xs mt-0.5" style={{ color: "var(--book-text-muted)" }}>
                    {svc.duration_minutes} min
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div
                    className="text-sm font-semibold"
                    style={{ color: "var(--book-primary)" }}
                  >
                    {formatBRL(svc.price)}
                  </div>
                </div>
              </div>
            </BookCard>
          ))}
          {options.length === 0 && (
            <p
              className="text-sm text-center py-8"
              style={{ color: "var(--book-text-muted)" }}
            >
              Nenhum serviço disponível no momento.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Etapa 2: Profissional ────────────────────────────────────────────────────

function ProfessionalStep({
  options,
  summary,
  loading,
  onBack,
  onSelect,
}: {
  options: ProfOpt[]
  summary: ContextSummary
  loading: boolean
  onBack: () => void
  onSelect: (opt: ProfOpt) => void
}) {
  return (
    <div>
      <StepHeader
        title="Com quem você prefere?"
        subtitle={summary.service_name ?? undefined}
        onBack={onBack}
      />
      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-3">
          {options.map((prof, i) => (
            <BookCard
              key={prof.row_key ?? `p-${i}`}
              onClick={() => onSelect(prof)}
              disabled={loading}
            >
              <div className="flex items-center gap-3">
                <div
                  className="h-10 w-10 rounded-full flex items-center justify-center font-bold text-sm shrink-0"
                  style={{
                    background: "var(--book-black-600)",
                    border: "1px solid var(--book-border)",
                    color: "var(--book-primary)",
                  }}
                >
                  {prof.name[0]}
                </div>
                <span className="font-medium" style={{ color: "var(--book-text)" }}>
                  {prof.name}
                </span>
              </div>
            </BookCard>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Etapa 3: Data ────────────────────────────────────────────────────────────

function DateStep({
  options,
  summary,
  loading,
  onBack,
  onSelect,
}: {
  options: DateOpt[]
  summary: ContextSummary
  loading: boolean
  onBack: () => void
  onSelect: (opt: DateOpt) => void
}) {
  const subtitle = [summary.service_name, summary.professional_name]
    .filter(Boolean)
    .join(" · ")

  const available = options.filter((d) => d.has_availability)
  const unavailableCount = options.length - available.length

  return (
    <div>
      <StepHeader
        title="Qual dia funciona para você?"
        subtitle={subtitle || undefined}
        onBack={onBack}
      />
      {loading ? (
        <Spinner />
      ) : (
        <div className="space-y-2">
          {available.length === 0 ? (
            <p
              className="text-sm py-8 text-center"
              style={{ color: "var(--book-text-muted)" }}
            >
              Nenhum dia disponível nos próximos 30 dias.
            </p>
          ) : (
            <>
              {available.map((d) => (
                <button
                  key={d.row_key}
                  onClick={() => onSelect(d)}
                  disabled={loading}
                  className="w-full text-left rounded-xl px-4 py-3 transition-all duration-150 disabled:opacity-40"
                  style={{
                    background: "var(--book-card)",
                    border: "1px solid var(--book-border)",
                  }}
                  onMouseEnter={(e) => {
                    ;(e.currentTarget as HTMLElement).style.borderColor =
                      "var(--book-primary)"
                  }}
                  onMouseLeave={(e) => {
                    ;(e.currentTarget as HTMLElement).style.borderColor =
                      "var(--book-border)"
                  }}
                >
                  <span className="font-medium" style={{ color: "var(--book-text)" }}>
                    {d.label}
                  </span>
                </button>
              ))}
              {unavailableCount > 0 && (
                <p className="text-xs pt-2" style={{ color: "var(--book-text-muted)" }}>
                  {unavailableCount} dia{unavailableCount > 1 ? "s" : ""} sem
                  disponibilidade no período.
                </p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Etapa 4: Horário ─────────────────────────────────────────────────────────

function TimeStep({
  options,
  summary,
  loading,
  error,
  onBack,
  onSelect,
}: {
  options: SlotOpt[]
  summary: ContextSummary
  loading: boolean
  error: string | null
  onBack: () => void
  onSelect: (opt: SlotOpt) => void
}) {
  // Formatar a data selecionada para o subtitle
  const dateLabel = summary.selected_date
    ? new Date(summary.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
        weekday: "long",
        day: "2-digit",
        month: "long",
      })
    : undefined

  return (
    <div>
      <StepHeader
        title="Escolha um horário"
        subtitle={dateLabel}
        onBack={onBack}
      />
      {error && <ErrorBanner msg={error} />}
      {loading ? (
        <Spinner />
      ) : options.length === 0 ? (
        <div className="text-center py-8">
          <p className="mb-4" style={{ color: "var(--book-text-secondary)" }}>
            Nenhum horário disponível neste dia.
          </p>
          <button
            onClick={onBack}
            className="text-sm underline"
            style={{ color: "var(--book-primary)" }}
          >
            Escolher outra data
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {options.map((slot) => (
            <button
              key={slot.row_key}
              onClick={() => onSelect(slot)}
              disabled={loading}
              className="rounded-xl py-3 text-sm font-medium transition-all duration-150 disabled:opacity-40"
              style={{
                background: "var(--book-card)",
                border: "1px solid var(--book-border)",
                color: "var(--book-text)",
              }}
              onMouseEnter={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                  "var(--book-primary)"
                ;(e.currentTarget as HTMLButtonElement).style.color =
                  "var(--book-primary)"
              }}
              onMouseLeave={(e) => {
                ;(e.currentTarget as HTMLButtonElement).style.borderColor =
                  "var(--book-border)"
                ;(e.currentTarget as HTMLButtonElement).style.color = "var(--book-text)"
              }}
            >
              {slot.start_display}
              <div
                className="text-xs truncate px-1 mt-0.5"
                style={{ color: "var(--book-text-muted)" }}
              >
                {slot.professional_name}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Etapa 5: Confirmar ───────────────────────────────────────────────────────

function ConfirmStep({
  summary,
  loading,
  error,
  onBack,
  onConfirm,
}: {
  summary: ContextSummary
  loading: boolean
  error: string | null
  onBack: () => void
  onConfirm: () => void
}) {
  return (
    <div>
      <StepHeader title="Confirmar agendamento" onBack={onBack} />

      {/* Resumo */}
      <div
        className="rounded-xl p-4 mb-6"
        style={{
          background: "var(--book-card)",
          border: "1px solid var(--book-border)",
          borderLeft: "3px solid var(--book-primary)",
        }}
      >
        <div className="font-semibold mb-3" style={{ color: "var(--book-text)" }}>
          {summary.service_name ?? "Serviço"}
        </div>
        <div className="text-sm space-y-1.5" style={{ color: "var(--book-text-secondary)" }}>
          {summary.professional_name && (
            <div>👤 {summary.professional_name}</div>
          )}
          {summary.selected_date && (
            <div>
              📅{" "}
              {new Date(summary.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
                weekday: "long",
                day: "2-digit",
                month: "long",
              })}
              {summary.slot_start_display && ` às ${summary.slot_start_display}`}
            </div>
          )}
          {summary.service_duration_minutes && (
            <div>⏱ {summary.service_duration_minutes} min</div>
          )}
        </div>
        {summary.service_price && (
          <div
            className="text-sm font-semibold mt-3 pt-3"
            style={{
              color: "var(--book-primary)",
              borderTop: "1px solid var(--book-border)",
            }}
          >
            {formatBRL(summary.service_price)}
          </div>
        )}
      </div>

      {error && <ErrorBanner msg={error} />}

      <button
        onClick={onConfirm}
        disabled={loading}
        className="book-btn-primary w-full py-3 text-sm"
      >
        {loading ? "Confirmando…" : "Confirmar agendamento"}
      </button>
    </div>
  )
}

// ─── Etapa 6: Confirmado ──────────────────────────────────────────────────────

function ConfirmedView({
  confirmation,
  token,
  onReset,
}: {
  confirmation: ConfirmData
  token: string
  onReset: () => void
}) {
  // Formatar data e hora
  function fmtDate(iso: string) {
    return new Date(iso).toLocaleString("pt-BR", {
      dateStyle: "full",
      timeStyle: "short",
    })
  }

  return (
    <div className="text-center py-6">
      <div
        className="w-16 h-16 rounded-full flex items-center justify-center text-2xl mx-auto mb-5"
        style={{
          background: "color-mix(in srgb, var(--book-primary) 15%, var(--book-card))",
          border: "1px solid var(--book-primary)",
        }}
      >
        ✓
      </div>

      <h2 className="text-2xl font-bold mb-1" style={{ color: "var(--book-text)" }}>
        Agendado!
      </h2>
      <p className="mb-8" style={{ color: "var(--book-text-secondary)" }}>
        Seu horário está confirmado.
      </p>

      <div
        className="rounded-2xl p-6 text-left space-y-3 mb-6"
        style={{
          background: "var(--book-card)",
          border: "1px solid var(--book-border)",
        }}
      >
        {[
          { label: "Serviço", value: confirmation.service_name },
          { label: "Profissional", value: confirmation.professional_name },
          { label: "Data e hora", value: fmtDate(confirmation.start_at) },
        ].map(({ label, value }) => (
          <div key={label} className="flex justify-between text-sm">
            <span style={{ color: "var(--book-text-muted)" }}>{label}</span>
            <span
              className="font-medium text-right"
              style={{ color: "var(--book-text)" }}
            >
              {value}
            </span>
          </div>
        ))}
        <div
          className="flex justify-between text-sm pt-3"
          style={{
            borderTop: "1px solid color-mix(in srgb, var(--book-primary) 20%, transparent)",
          }}
        >
          <span style={{ color: "var(--book-text-muted)" }}>Total</span>
          <span className="font-bold" style={{ color: "var(--book-primary)" }}>
            {formatBRL(confirmation.total_amount)}
          </span>
        </div>
      </div>

      <p className="text-xs mb-6" style={{ color: "var(--book-text-muted)" }}>
        Código:{" "}
        <span className="font-mono" style={{ color: "var(--book-text-secondary)" }}>
          {token.slice(0, 8).toUpperCase()}
        </span>
      </p>

      <button
        onClick={onReset}
        className="text-sm underline"
        style={{ color: "var(--book-primary)" }}
      >
        Fazer outro agendamento
      </button>
    </div>
  )
}

// ─── Etapa: Cancelado ─────────────────────────────────────────────────────────

function CancelledView({ onReset }: { onReset: () => void }) {
  return (
    <div className="text-center py-6">
      <div className="text-4xl mb-4">✕</div>
      <h2 className="text-xl font-bold mb-2" style={{ color: "var(--book-text)" }}>
        Agendamento cancelado
      </h2>
      <p className="mb-8 text-sm" style={{ color: "var(--book-text-secondary)" }}>
        Seu agendamento foi cancelado com sucesso.
      </p>
      <button
        onClick={onReset}
        className="book-btn-primary px-6 py-3 text-sm"
      >
        Fazer novo agendamento
      </button>
    </div>
  )
}
