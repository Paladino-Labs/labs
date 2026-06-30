"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { addDays, format, isSameDay, startOfDay } from "date-fns"
import { ptBR } from "date-fns/locale/pt-BR"
import { ArrowLeft, Check, CheckCircle2, Clock, Scissors, User } from "lucide-react"
import { publicFetch } from "@/lib/api"
import { getPortalToken } from "@/lib/portal-api"
import { cn, formatBRL, formatPhoneBR } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { CrossSellStep } from "@/components/booking/CrossSellStep"
import { ThemeToggle } from "@/components/booking/ThemeToggle"

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface ServiceOpt {
  id: string
  name: string
  price: string
  duration_minutes: number
  description?: string | null
  row_key: string
}

interface ProfOpt {
  id: string | null
  name: string
  description?: string | null
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

type SrvState =
  | "IDLE"
  | "AWAITING_SERVICE"
  | "AWAITING_PROFESSIONAL"
  | "AWAITING_DATE"
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
  manage_url?: string | null  // NOVO — link de gestão via WhatsApp (Sprint B1)
}

export interface Session {
  session_id: string
  token: string
  state: SrvState
  options: (ServiceOpt | ProfOpt | DateOpt | SlotOpt)[]
  context_summary: ContextSummary
  confirmation: ConfirmData | null
  expires_at: string
  company_timezone: string
  booking_code?: string | null
  error?: string | null
  dates_has_next?: boolean
  dates_has_previous?: boolean
}

// ─── Stepper ──────────────────────────────────────────────────────────────────

const STEP_LABELS = ["Serviço", "Barbeiro", "Horário", "Confirmar"]

function BookingStepper({ currentStep }: { currentStep: 1 | 2 | 3 | 4 }) {
  return (
    <div className="flex items-center gap-2 mb-8">
      {STEP_LABELS.map((label, i) => {
        const n = (i + 1) as 1 | 2 | 3 | 4
        const done = currentStep > n
        const active = currentStep === n
        return (
          <div key={label} className="flex flex-1 items-center gap-2">
            <div className={cn(
              "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-medium shrink-0",
              done   && "border-primary bg-primary text-primary-foreground",
              active && "border-primary text-primary",
              !done && !active && "border-border text-muted-foreground",
            )}>
              {done ? <Check className="h-3 w-3" /> : n}
            </div>
            <span className={cn(
              "hidden sm:block text-xs",
              active ? "text-foreground" : "text-muted-foreground",
            )}>
              {label}
            </span>
            {n < STEP_LABELS.length && (
              <div className={cn("h-px flex-1", done ? "bg-primary" : "bg-border")} />
            )}
          </div>
        )
      })}
    </div>
  )
}

function fsmToStep(state: SrvState): 1 | 2 | 3 | 4 {
  if (state === "AWAITING_SERVICE")                             return 1
  if (state === "AWAITING_PROFESSIONAL")                        return 2
  if (state === "AWAITING_DATE" || state === "AWAITING_TIME")   return 3
  return 4
}

// ─── ErrorBanner ──────────────────────────────────────────────────────────────

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive">
      {message}
    </div>
  )
}

// ─── Componente principal ─────────────────────────────────────────────────────

export default function BookingFlow({
  slug,
  companyName,
  initialToken,
  onTokenChange,
  initialServiceId,
}: {
  slug: string
  companyName: string
  initialToken?: string | null
  onTokenChange?: (token: string) => void
  initialServiceId?: string | null
}) {
  const [session,      setSession]      = useState<Session | null>(null)
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState<string | null>(null)
  const [custName,     setCustName]     = useState("")
  const [custPhone,    setCustPhone]    = useState("")
  const [custEmail,    setCustEmail]    = useState("")
  const [selectedDate, setSelectedDate] = useState<Date | null>(startOfDay(new Date()))
  const autoSelectedRef = useRef(false)
  // Garante UMA única criação/retomada de sessão no mount. Sem isso, o React
  // StrictMode (dev) invoca o efeito 2× e cria 2 sessões de booking no backend;
  // o merge de setSession mistura session_id de uma com o state de outra →
  // SELECT_PROFESSIONAL chega numa sessão ainda em AWAITING_SERVICE (422).
  const bootstrappedRef = useRef(false)
  // Auto-seleciona o dia de hoje na primeira entrada em AWAITING_DATE — assim o
  // cliente cai direto nos horários do dia pré-selecionado (menos cliques).
  const autoDateRef = useRef(false)

  // IDs locais para cross-sell (não estão no context_summary)
  const [localServiceId,      setLocalServiceId]      = useState<string | null>(null)
  const [localProfessionalId, setLocalProfessionalId] = useState<string | null>(null)
  // Flag de UI: mostrar Tela 4 (cross-sell) antes de AWAITING_CUSTOMER
  const [showCrossSell, setShowCrossSell] = useState(false)
  // Cliente logado no portal → gerencia o agendamento no portal (não pelo link).
  const [portalLoggedIn, setPortalLoggedIn] = useState(false)
  useEffect(() => { setPortalLoggedIn(!!getPortalToken()) }, [])

  const next14Days = Array.from({ length: 14 }, (_, i) => addDays(startOfDay(new Date()), i))

  // ── Iniciar ou retomar sessão ─────────────────────────────────────────────
  useEffect(() => {
    if (bootstrappedRef.current) return
    bootstrappedRef.current = true
    if (initialToken) {
      publicFetch<Session>(`/booking/${slug}/session/${initialToken}`)
        .then(s => {
          setSession(s)
          if (s.context_summary.selected_date) {
            setSelectedDate(startOfDay(new Date(s.context_summary.selected_date + "T12:00:00")))
          }
        })
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
      const result = await publicFetch<Session>(`/booking/${slug}/start`, {
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
        const result = await publicFetch<Partial<Session>>(`/booking/${slug}/update`, {
          method: "POST",
          body: JSON.stringify({ session_id: session.session_id, action, payload }),
        })
        setSession(prev => prev ? { ...prev, ...result } : null)
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

  // Auto-seleciona serviço ao montar quando vindo do botão "Agendar" da vitrine
  useEffect(() => {
    if (
      initialServiceId &&
      !autoSelectedRef.current &&
      session?.state === "AWAITING_SERVICE"
    ) {
      autoSelectedRef.current = true
      setLocalServiceId(initialServiceId)
      dispatch("SELECT_SERVICE", { service_id: initialServiceId })
    }
  }, [session?.state, initialServiceId, dispatch])

  // Reseta data selecionada quando o dia está fechado (zero slots retornados)
  useEffect(() => {
    if (session?.state === "AWAITING_TIME" && session.options.length === 0) {
      setSelectedDate(null)
    }
  }, [session?.state, session?.options])

  // Tela 4 — ativa o cross-sell ao entrar em AWAITING_CUSTOMER (skip silencioso
  // se não houver pacotes/planos é feito dentro do próprio CrossSellStep).
  useEffect(() => {
    if (session?.state === "AWAITING_CUSTOMER" && localServiceId) {
      setShowCrossSell(true)
    }
  }, [session?.state, localServiceId])

  // Tela Horário — ao chegar em AWAITING_DATE, seleciona o dia de hoje uma vez
  // para já exibir os slots (o cliente só clica no horário se o dia for este).
  useEffect(() => {
    if (session?.state === "AWAITING_DATE" && !autoDateRef.current) {
      autoDateRef.current = true
      const todayStr = format(startOfDay(new Date()), "yyyy-MM-dd")
      const opts = (session.options ?? []) as DateOpt[]
      const opt = opts.find(o => o.date === todayStr)
      dispatch("SELECT_DATE", opt ? { date: opt.date, row_key: opt.row_key } : { date: todayStr })
    }
  }, [session?.state, session?.options, dispatch])

  function handleSelectDate(d: Date) {
    setSelectedDate(d)
    const dateStr = format(d, "yyyy-MM-dd")
    const opts = (session?.options ?? []) as DateOpt[]
    const opt = opts.find(o => o.date === dateStr)
    if (opt) {
      dispatch("SELECT_DATE", { date: opt.date, row_key: opt.row_key })
    } else {
      dispatch("SELECT_DATE", { date: dateStr })
    }
  }

  // ── Sem sessão ────────────────────────────────────────────────────────────
  if (!session) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        {loading && <p className="text-sm text-muted-foreground">Carregando…</p>}
        {error && (
          <div className="text-center px-6 space-y-4">
            <ErrorBanner message={error} />
            <button onClick={startNewSession}
              className="rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors">
              Tentar novamente
            </button>
          </div>
        )}
      </div>
    )
  }

  const showStepper = !["IDLE", "CONFIRMED", "CANCELLED"].includes(session.state)
  const ctx = session.context_summary

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-background text-foreground">

      {/* Header — esquerda volta à vitrine; direita: wordmark + tema */}
      <header className="border-b border-border">
        <div className="mx-auto grid max-w-3xl grid-cols-[1fr_auto_1fr] items-center px-6 py-4">
          <a href={`/book/${slug}`}
            className="inline-flex min-w-0 items-center gap-2 justify-self-start text-sm text-muted-foreground hover:text-foreground transition-colors">
            <ArrowLeft className="h-4 w-4 shrink-0" />
            <span className="truncate">{companyName || "Voltar"}</span>
          </a>
          <span className="justify-self-center font-display text-2xl tracking-[0.3em] text-primary leading-none">
            PALADINO
          </span>
          <div className="justify-self-end">
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Conteúdo */}
      <div className="mx-auto max-w-3xl px-6 py-8">

        {showStepper && <BookingStepper currentStep={fsmToStep(session.state)} />}

        {error && (
          <div className="mb-4">
            <ErrorBanner message={error} />
          </div>
        )}

        {/* ── Step 1 — Serviço ────────────────────────────────────────────── */}
        {session.state === "AWAITING_SERVICE" && (
          <div>
            <h2 className="font-display text-2xl tracking-wide mb-4">Escolha o serviço</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {(session.options as ServiceOpt[]).map(s => (
                <button key={s.row_key}
                  onClick={() => {
                    setLocalServiceId(s.id)
                    dispatch("SELECT_SERVICE", { service_id: s.id })
                  }}
                  disabled={loading}
                  className="text-left rounded-lg border border-border bg-card p-4 transition-all hover:border-primary disabled:opacity-40">
                  <div className="flex items-start justify-between">
                    <div>
                      <p className="font-semibold">{s.name}</p>
                      {s.description && (
                        <p className="text-xs text-muted-foreground mt-1">{s.description}</p>
                      )}
                    </div>
                    <Scissors className="h-4 w-4 text-primary shrink-0" />
                  </div>
                  <div className="mt-3 flex items-center justify-between">
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="h-3 w-3" /> {s.duration_minutes} min
                    </span>
                    <span className="font-display text-lg text-primary">
                      {formatBRL(s.price)}
                    </span>
                  </div>
                </button>
              ))}
              {session.options.length === 0 && (
                <p className="text-sm text-center text-muted-foreground py-8 col-span-2">
                  Nenhum serviço disponível no momento.
                </p>
              )}
            </div>
          </div>
        )}

        {/* ── Step 2 — Barbeiro ────────────────────────────────────────────── */}
        {session.state === "AWAITING_PROFESSIONAL" && (
          <div>
            <h2 className="font-display text-2xl tracking-wide mb-4">Escolha o barbeiro</h2>
            <div className="grid gap-3 sm:grid-cols-2">
              {(session.options as ProfOpt[]).map(p => (
                <button key={p.row_key}
                  onClick={() => dispatch("SELECT_PROFESSIONAL", { professional_id: p.id ?? "any" })}
                  disabled={loading}
                  className="text-left rounded-lg border border-border bg-card p-4 transition-all hover:border-primary disabled:opacity-40">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15 text-sm font-semibold text-primary shrink-0">
                      {p.name === "Qualquer disponível"
                        ? <User className="h-5 w-5" />
                        : p.name.split(" ").map(n => n[0]).slice(0, 2).join("")}
                    </div>
                    <div>
                      <p className="font-semibold">{p.name}</p>
                      {p.description && (
                        <p className="text-xs text-muted-foreground">{p.description}</p>
                      )}
                    </div>
                  </div>
                </button>
              ))}
            </div>
            <div className="flex justify-start pt-6">
              <button onClick={handleBack}
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ArrowLeft className="h-4 w-4" /> Voltar
              </button>
            </div>
          </div>
        )}

        {/* ── Step 3 — Horário (AWAITING_DATE + AWAITING_TIME) ────────────── */}
        {(session.state === "AWAITING_DATE" || session.state === "AWAITING_TIME") && (
          <div className="space-y-6">

            {/* Picker de datas — 14 dias */}
            <div>
              <h2 className="font-display text-2xl tracking-wide mb-4">Escolha o dia</h2>
              <div className="grid grid-cols-4 gap-2 sm:grid-cols-7">
                {next14Days.map(d => {
                  const active = selectedDate !== null && isSameDay(d, selectedDate)
                  return (
                    <button key={d.toISOString()}
                      onClick={() => handleSelectDate(d)}
                      disabled={loading}
                      className={cn(
                        "flex flex-col items-center rounded-lg border p-3 transition-all disabled:opacity-40",
                        active
                          ? "border-primary bg-primary/10"
                          : "border-border hover:bg-accent",
                      )}>
                      <span className="text-[10px] uppercase tracking-widest text-muted-foreground">
                        {format(d, "EEE", { locale: ptBR })}
                      </span>
                      <span className="font-display text-2xl">
                        {format(d, "d")}
                      </span>
                      <span className="text-[10px] text-muted-foreground">
                        {format(d, "MMM", { locale: ptBR })}
                      </span>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Slots — só exibir em AWAITING_TIME */}
            {session.state === "AWAITING_TIME" && (
              <div>
                <h3 className="font-semibold mb-3">Horários disponíveis</h3>
                {(session.options as SlotOpt[]).length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Sem horários disponíveis neste dia. Escolha outra data.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {(session.options as SlotOpt[]).map(slot => (
                      <button key={slot.row_key}
                        onClick={() => {
                          setLocalProfessionalId(slot.professional_id)
                          dispatch("SELECT_TIME", {
                            start_at: slot.start_at,
                            end_at: slot.end_at,
                            professional_id: slot.professional_id,
                            row_key: slot.row_key,
                          })
                        }}
                        disabled={loading}
                        className="rounded-md border border-border px-4 py-2 font-mono text-sm hover:border-primary hover:bg-primary/5 transition-all disabled:opacity-40">
                        {slot.start_display}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="flex justify-start pt-4">
              <button onClick={handleBack}
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ArrowLeft className="h-4 w-4" /> Voltar
              </button>
            </div>
          </div>
        )}

        {/* ── Tela 4 — Cross-sell contextual ──────────────────────────────── */}
        {showCrossSell && session.state === "AWAITING_CUSTOMER" && (
          <CrossSellStep
            slug={slug}
            serviceId={localServiceId!}
            serviceName={ctx.service_name ?? ""}
            servicePrice={ctx.service_price ?? "0"}
            professionalId={localProfessionalId}
            professionalName={ctx.professional_name ?? null}
            startAt={ctx.slot_start_at ?? ""}
            endAt={ctx.slot_end_at ?? ""}
            onConfirmOnly={() => setShowCrossSell(false)}
          />
        )}

        {/* ── Step 4a — Dados do cliente (AWAITING_CUSTOMER) ──────────────── */}
        {!showCrossSell && session.state === "AWAITING_CUSTOMER" && (
          <div className="space-y-6">
            <h2 className="font-display text-2xl tracking-wide">Seus dados</h2>

            {/* Resumo */}
            <div className="rounded-lg border-l-4 border-primary bg-card p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Serviço</span>
                <span className="font-medium">{ctx.service_name}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Barbeiro</span>
                <span className="font-medium">{ctx.professional_name}</span>
              </div>
              {ctx.selected_date && ctx.slot_start_display && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Quando</span>
                  <span className="font-medium text-right">
                    {new Date(ctx.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
                      weekday: "long", day: "2-digit", month: "long",
                      timeZone: session.company_timezone,
                    })} às {ctx.slot_start_display}
                  </span>
                </div>
              )}
              {ctx.service_price && (
                <div className="flex justify-between border-t border-border pt-2 mt-1">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-display text-lg text-primary">
                    {formatBRL(ctx.service_price)}
                  </span>
                </div>
              )}
            </div>

            {/* Formulário */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="name">Nome completo</Label>
                <Input id="name" value={custName} onChange={e => setCustName(e.target.value)}
                  placeholder="Seu nome completo" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="phone">Telefone</Label>
                <Input id="phone" value={custPhone} onChange={e => setCustPhone(formatPhoneBR(e.target.value))}
                  placeholder="(11) 90000-0000" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="email">E-mail (opcional)</Label>
                <Input id="email" type="email" value={custEmail}
                  onChange={e => setCustEmail(e.target.value)}
                  placeholder="seu@email.com" />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button onClick={handleBack}
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ArrowLeft className="h-4 w-4" /> Voltar
              </button>
              <Button
                onClick={() => dispatch("SET_CUSTOMER", { name: custName, phone: custPhone })}
                disabled={!custName || !custPhone || loading}
                className="px-8">
                {loading ? "Aguarde…" : "Continuar"}
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 4b — Confirmação (AWAITING_CONFIRMATION) ───────────────── */}
        {session.state === "AWAITING_CONFIRMATION" && (
          <div className="space-y-6">
            <h2 className="font-display text-2xl tracking-wide">Confirmar agendamento</h2>

            <div className="rounded-lg border-l-4 border-primary bg-card p-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Serviço</span>
                <span className="font-medium">{ctx.service_name}</span>
              </div>
              {ctx.customer_name && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Cliente</span>
                  <span className="font-medium">{ctx.customer_name}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-muted-foreground">Barbeiro</span>
                <span className="font-medium">{ctx.professional_name}</span>
              </div>
              {ctx.selected_date && ctx.slot_start_display && (
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Quando</span>
                  <span className="font-medium text-right">
                    {new Date(ctx.selected_date + "T12:00:00").toLocaleDateString("pt-BR", {
                      weekday: "long", day: "2-digit", month: "long",
                      timeZone: session.company_timezone,
                    })} às {ctx.slot_start_display}
                  </span>
                </div>
              )}
              {ctx.service_price && (
                <div className="flex justify-between border-t border-border pt-2 mt-1">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-display text-lg text-primary">
                    {formatBRL(ctx.service_price)}
                  </span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-2">
              <button onClick={handleBack}
                className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors">
                <ArrowLeft className="h-4 w-4" /> Voltar
              </button>
              <Button onClick={() => dispatch("CONFIRM")} disabled={loading} className="px-8">
                {loading ? "Confirmando…" : "Confirmar agendamento"}
                {!loading && <Check className="ml-2 h-4 w-4" />}
              </Button>
            </div>
          </div>
        )}

        {/* ── Confirmado (CONFIRMED) ───────────────────────────────────────── */}
        {session.state === "CONFIRMED" && (
          <div className="flex flex-col items-center text-center py-12 space-y-4">
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-success/15 text-success">
              <CheckCircle2 className="h-8 w-8" />
            </div>
            <h1 className="font-display text-4xl tracking-wide">
              Agendamento confirmado!
            </h1>
            {portalLoggedIn ? (
              <p className="text-muted-foreground max-w-sm text-sm">
                Acompanhe e gerencie seu agendamento no Painel do Cliente.
              </p>
            ) : session.confirmation?.manage_url ? (
              <p className="text-muted-foreground max-w-sm text-sm">
                📱 Enviamos o link de gestão para o seu WhatsApp.
              </p>
            ) : (
              <p className="text-muted-foreground max-w-sm text-sm">
                Você receberá uma confirmação em breve.
              </p>
            )}
            {session.confirmation && (
              <div className="rounded-2xl border border-border bg-card p-6 text-left space-y-3 w-full max-w-sm text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Serviço</span>
                  <span className="font-medium">{session.confirmation.service_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Barbeiro</span>
                  <span className="font-medium">{session.confirmation.professional_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Data e hora</span>
                  <span className="font-medium text-right">
                    {new Date(session.confirmation.start_at).toLocaleString("pt-BR", {
                      dateStyle: "short", timeStyle: "short",
                      timeZone: session.company_timezone,
                    })}
                  </span>
                </div>
                <div className="flex justify-between border-t border-border pt-2 mt-1">
                  <span className="text-muted-foreground">Total</span>
                  <span className="font-display text-lg text-primary">
                    {formatBRL(session.confirmation.total_amount)}
                  </span>
                </div>
              </div>
            )}
            <p className="font-mono text-xs text-muted-foreground">
              Código: {(session.booking_code ?? session.token.slice(0, 8)).toUpperCase()}
            </p>
            <a
              href={portalLoggedIn ? "/portal/dashboard" : "/portal/login"}
              className="book-btn-secondary px-4 py-2 text-sm inline-flex items-center gap-2">
              {portalLoggedIn ? "Gerenciar no Painel do Cliente" : "Acessar Painel do Cliente"}
            </a>
            <button onClick={handleReset}
              className="mt-4 rounded-md border border-border px-4 py-2 text-sm hover:bg-accent transition-colors">
              Fazer novo agendamento
            </button>
          </div>
        )}

        {/* ── Cancelado (CANCELLED) ────────────────────────────────────────── */}
        {session.state === "CANCELLED" && (
          <div className="flex flex-col items-center text-center py-12 space-y-4">
            <h2 className="font-display text-2xl">Agendamento cancelado</h2>
            <p className="text-sm text-muted-foreground">
              Seu agendamento foi cancelado com sucesso.
            </p>
            <Button onClick={handleReset} variant="outline">
              Fazer novo agendamento
            </Button>
          </div>
        )}

      </div>
    </div>
  )
}
