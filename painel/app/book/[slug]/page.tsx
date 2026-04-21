"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams } from "next/navigation"
import { formatBRL } from "@/lib/utils"

// ─── Types ────────────────────────────────────────────────────────────────────

interface CompanyInfo {
  name: string
  slug: string
  online_booking_enabled: boolean
}

interface ServiceInfo {
  id: string
  name: string
  price: string
  duration_minutes: number
  description?: string
  image_url?: string
}

interface ProfessionalInfo {
  id: string | null   // null = "Qualquer disponível"
  name: string
}

interface SlotInfo {
  start_at: string
  end_at: string
  professional_id: string
  professional_name: string
}

interface BookingConfirmation {
  token: string
  appointment_id: string
  service_name: string
  professional_name: string
  start_at: string
  end_at: string
  total_amount: string
}

// ─── Step type ────────────────────────────────────────────────────────────────

type Step = "service" | "professional" | "date" | "time" | "customer" | "confirmed"

// ─── API base ─────────────────────────────────────────────────────────────────

const API = process.env.NEXT_PUBLIC_API_URL!

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail ?? "Erro desconhecido")
  }
  return res.json()
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "full", timeStyle: "short" })
}

function addDays(base: Date, n: number): Date {
  const d = new Date(base)
  d.setDate(d.getDate() + n)
  return d
}

function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10)
}

// ─── Sub-componentes visuais ──────────────────────────────────────────────────

function StepHeader({ title, subtitle, onBack }: {
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
      <h2 className="text-xl font-bold" style={{ color: "var(--book-text)" }}>{title}</h2>
      {subtitle && (
        <p className="text-sm mt-1" style={{ color: "var(--book-text-secondary)" }}>{subtitle}</p>
      )}
    </div>
  )
}

function BookCard({
  children,
  onClick,
  selected,
}: {
  children: React.ReactNode
  onClick?: () => void
  selected?: boolean
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-xl p-4 transition-all duration-150"
      style={{
        background: "var(--book-card)",
        border: selected
          ? "1px solid var(--book-primary)"
          : "1px solid var(--book-border)",
        boxShadow: selected
          ? "0 0 0 2px color-mix(in srgb, var(--book-primary) 20%, transparent)"
          : "none",
      }}
    >
      {children}
    </button>
  )
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function BookingPage() {
  const { slug } = useParams<{ slug: string }>()

  // Company
  const [company, setCompany] = useState<CompanyInfo | null>(null)
  const [companyError, setCompanyError] = useState<string | null>(null)

  // Wizard state
  const [step, setStep] = useState<Step>("service")
  const [services, setServices] = useState<ServiceInfo[]>([])
  const [professionals, setProfessionals] = useState<ProfessionalInfo[]>([])
  const [slots, setSlots] = useState<SlotInfo[]>([])

  const [selectedService, setSelectedService] = useState<ServiceInfo | null>(null)
  const [selectedProfessional, setSelectedProfessional] = useState<ProfessionalInfo | null>(null)
  const [selectedDate, setSelectedDate] = useState<string>("")
  const [selectedSlot, setSelectedSlot] = useState<SlotInfo | null>(null)

  // Customer form
  const [customerName, setCustomerName] = useState("")
  const [customerPhone, setCustomerPhone] = useState("")
  const [customerEmail, setCustomerEmail] = useState("")

  // UI state
  const [loadingServices, setLoadingServices] = useState(false)
  const [loadingProfs, setLoadingProfs] = useState(false)
  const [loadingSlots, setLoadingSlots] = useState(false)
  const [booking, setBooking] = useState(false)
  const [bookingError, setBookingError] = useState<string | null>(null)
  const [confirmation, setConfirmation] = useState<BookingConfirmation | null>(null)

  // Date navigation — lógica inalterada
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const [dateOffset, setDateOffset] = useState(0)
  const DATES_SHOWN = 7

  const visibleDates = Array.from({ length: DATES_SHOWN }, (_, i) =>
    addDays(today, dateOffset + i)
  )

  // ── Load company ─────────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch<CompanyInfo>(`/public/${slug}/info`)
      .then(setCompany)
      .catch((e) => setCompanyError(e.message))
  }, [slug])

  // ── Load services ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!company) return
    setLoadingServices(true)
    apiFetch<ServiceInfo[]>(`/public/${slug}/services`)
      .then(setServices)
      .catch(() => {})
      .finally(() => setLoadingServices(false))
  }, [company, slug])

  // ── Load professionals when service selected ──────────────────────────────────
  const loadProfessionals = useCallback(
    async (serviceId: string) => {
      setLoadingProfs(true)
      try {
        const data = await apiFetch<ProfessionalInfo[]>(
          `/public/${slug}/professionals?service_id=${serviceId}`
        )
        setProfessionals(data)
      } finally {
        setLoadingProfs(false)
      }
    },
    [slug]
  )

  // ── Load slots ───────────────────────────────────────────────────────────────
  const loadSlots = useCallback(
    async (serviceId: string, professionalId: string | null, date: string) => {
      setLoadingSlots(true)
      setSlots([])
      try {
        const profParam = professionalId ? `&professional_id=${professionalId}` : ""
        const data = await apiFetch<SlotInfo[]>(
          `/public/${slug}/slots?service_id=${serviceId}&date=${date}${profParam}`
        )
        setSlots(data)
      } finally {
        setLoadingSlots(false)
      }
    },
    [slug]
  )

  // ── Date selected → load slots ──────────────────────────────────────────────
  useEffect(() => {
    if (step === "time" && selectedService && selectedDate) {
      loadSlots(selectedService.id, selectedProfessional?.id ?? null, selectedDate)
    }
  }, [step, selectedService, selectedProfessional, selectedDate, loadSlots])

  // ── Step handlers — lógica inalterada ────────────────────────────────────────

  function handleSelectService(svc: ServiceInfo) {
    setSelectedService(svc)
    setSelectedProfessional(null)
    setSelectedDate("")
    setSelectedSlot(null)
    loadProfessionals(svc.id)
    setStep("professional")
  }

  function handleSelectProfessional(prof: ProfessionalInfo) {
    setSelectedProfessional(prof)
    setSelectedDate(isoDate(today))
    setStep("date")
  }

  function handleSelectDate(d: Date) {
    const iso = isoDate(d)
    setSelectedDate(iso)
    setSelectedSlot(null)
    setStep("time")
  }

  function handleSelectSlot(slot: SlotInfo) {
    setSelectedSlot(slot)
    setStep("customer")
  }

  async function handleBook(e: React.FormEvent) {
    e.preventDefault()
    if (!selectedService || !selectedSlot) return
    setBookingError(null)
    setBooking(true)

    const professionalId = selectedSlot.professional_id

    try {
      const result = await apiFetch<BookingConfirmation>(`/public/${slug}/book`, {
        method: "POST",
        body: JSON.stringify({
          service_id: selectedService.id,
          professional_id: professionalId,
          start_at: selectedSlot.start_at,
          customer_name: customerName,
          customer_phone: customerPhone,
          customer_email: customerEmail || undefined,
        }),
      })
      setConfirmation(result)
      setStep("confirmed")
    } catch (err: unknown) {
      setBookingError((err as Error).message)
    } finally {
      setBooking(false)
    }
  }

  // ── Render ────────────────────────────────────────────────────────────────────

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
          <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>{companyError}</p>
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
        <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>Carregando…</p>
      </div>
    )
  }

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
            {company.name}
          </h1>
          <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
            Agendamento online
          </p>
        </div>
      </div>

      {/* ── Barra de progresso ────────────────────────────────────────────────── */}
      {step !== "confirmed" && (
        <div className="max-w-lg mx-auto px-6 pt-4">
          <div className="flex gap-1">
            {(["service", "professional", "date", "time", "customer"] as Step[]).map((s, i) => {
              const steps: Step[] = ["service", "professional", "date", "time", "customer"]
              const active = steps.indexOf(step) >= i
              return (
                <div
                  key={s}
                  className="h-0.5 flex-1 rounded-full transition-colors duration-300"
                  style={{
                    background: active
                      ? "var(--book-gradient-gold)"
                      : "var(--book-border)",
                  }}
                />
              )
            })}
          </div>
        </div>
      )}

      <div className="max-w-lg mx-auto px-6 py-8">

        {/* ── Step 1: Serviço ───────────────────────────────────────────────── */}
        {step === "service" && (
          <div>
            <StepHeader title="Qual serviço você quer agendar?" />

            {loadingServices ? (
              <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
                Carregando serviços…
              </p>
            ) : (
              <div className="space-y-3">
                {services.map((svc) => (
                  <BookCard key={svc.id} onClick={() => handleSelectService(svc)}>
                    <div className="flex gap-4 items-center">
                      {svc.image_url ? (
                        <img
                          src={svc.image_url}
                          alt={svc.name}
                          className="h-12 w-12 rounded-lg object-cover shrink-0"
                        />
                      ) : (
                        <div
                          className="h-12 w-12 rounded-lg flex items-center justify-center text-xl shrink-0"
                          style={{
                            background: "var(--book-black-600)",
                            border: "1px solid var(--book-border)",
                          }}
                        >
                          ✂️
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold" style={{ color: "var(--book-text)" }}>
                          {svc.name}
                        </div>
                        {svc.description && (
                          <div
                            className="text-xs mt-0.5 truncate"
                            style={{ color: "var(--book-text-muted)" }}
                          >
                            {svc.description}
                          </div>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-sm font-semibold" style={{ color: "var(--book-primary)" }}>
                          {formatBRL(svc.price)}
                        </div>
                        <div className="text-xs" style={{ color: "var(--book-text-muted)" }}>
                          {svc.duration_minutes} min
                        </div>
                      </div>
                    </div>
                  </BookCard>
                ))}

                {services.length === 0 && (
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
        )}

        {/* ── Step 2: Profissional ──────────────────────────────────────────── */}
        {step === "professional" && (
          <div>
            <StepHeader
              title="Com quem você prefere?"
              subtitle={selectedService?.name}
              onBack={() => setStep("service")}
            />

            {loadingProfs ? (
              <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
                Carregando…
              </p>
            ) : (
              <div className="space-y-3">
                {professionals.map((prof, i) => (
                  <BookCard key={prof.id ?? `any-${i}`} onClick={() => handleSelectProfessional(prof)}>
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
        )}

        {/* ── Step 3: Data ──────────────────────────────────────────────────── */}
        {step === "date" && (
          <div>
            <StepHeader
              title="Qual dia funciona para você?"
              subtitle={`${selectedService?.name} · ${selectedProfessional?.name}`}
              onBack={() => setStep("professional")}
            />

            {/* Seletor de datas */}
            <div className="flex gap-2 overflow-x-auto pb-2 mb-6">
              {visibleDates.map((d) => {
                const iso = isoDate(d)
                const isSelected = iso === selectedDate
                const isToday = iso === isoDate(today)
                return (
                  <button
                    key={iso}
                    onClick={() => handleSelectDate(d)}
                    className="flex flex-col items-center rounded-xl px-3 py-2.5 min-w-[62px] transition-all duration-150"
                    style={{
                      background: isSelected ? "color-mix(in srgb, var(--book-primary) 12%, var(--book-card))" : "var(--book-card)",
                      border: isSelected ? "1px solid var(--book-primary)" : "1px solid var(--book-border)",
                      color: isSelected ? "var(--book-primary)" : "var(--book-text-secondary)",
                    }}
                  >
                    <span className="text-xs font-medium uppercase">
                      {d.toLocaleDateString("pt-BR", { weekday: "short" })}
                    </span>
                    <span className="text-lg font-bold leading-tight">{d.getDate()}</span>
                    <span className="text-xs">{d.toLocaleDateString("pt-BR", { month: "short" })}</span>
                    {isToday && (
                      <span className="text-[10px] mt-0.5" style={{ color: "var(--book-primary)" }}>
                        hoje
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* Navegação entre semanas */}
            <div className="flex justify-between text-sm mb-6">
              <button
                onClick={() => setDateOffset((o) => Math.max(0, o - DATES_SHOWN))}
                disabled={dateOffset === 0}
                className="transition-opacity disabled:opacity-30"
                style={{ color: "var(--book-primary)" }}
              >
                ← Anterior
              </button>
              <button
                onClick={() => setDateOffset((o) => o + DATES_SHOWN)}
                style={{ color: "var(--book-primary)" }}
              >
                Próximos →
              </button>
            </div>

            {selectedDate && (
              <button
                onClick={() => setStep("time")}
                className="book-btn-primary w-full py-3 text-sm"
              >
                Ver horários disponíveis →
              </button>
            )}
          </div>
        )}

        {/* ── Step 4: Horário ───────────────────────────────────────────────── */}
        {step === "time" && (
          <div>
            <StepHeader
              title="Escolha um horário"
              subtitle={
                selectedDate
                  ? new Date(selectedDate + "T12:00:00").toLocaleDateString("pt-BR", {
                      weekday: "long",
                      day: "2-digit",
                      month: "long",
                    })
                  : ""
              }
              onBack={() => setStep("date")}
            />

            {loadingSlots ? (
              <p className="text-sm" style={{ color: "var(--book-text-muted)" }}>
                Buscando horários…
              </p>
            ) : slots.length === 0 ? (
              <div className="text-center py-8">
                <p className="mb-4" style={{ color: "var(--book-text-secondary)" }}>
                  Nenhum horário disponível neste dia.
                </p>
                <button
                  onClick={() => setStep("date")}
                  className="text-sm underline"
                  style={{ color: "var(--book-primary)" }}
                >
                  Escolher outra data
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {slots.map((slot, i) => {
                  const time = new Date(slot.start_at).toLocaleTimeString("pt-BR", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                  return (
                    <button
                      key={i}
                      onClick={() => handleSelectSlot(slot)}
                      className="rounded-xl py-3 text-sm font-medium transition-all duration-150"
                      style={{
                        background: "var(--book-card)",
                        border: "1px solid var(--book-border)",
                        color: "var(--book-text)",
                      }}
                      onMouseEnter={(e) => {
                        ;(e.currentTarget as HTMLButtonElement).style.borderColor = "var(--book-primary)"
                        ;(e.currentTarget as HTMLButtonElement).style.color = "var(--book-primary)"
                      }}
                      onMouseLeave={(e) => {
                        ;(e.currentTarget as HTMLButtonElement).style.borderColor = "var(--book-border)"
                        ;(e.currentTarget as HTMLButtonElement).style.color = "var(--book-text)"
                      }}
                    >
                      {time}
                      {!selectedProfessional?.id && (
                        <div
                          className="text-xs truncate px-1 mt-0.5"
                          style={{ color: "var(--book-text-muted)" }}
                        >
                          {slot.professional_name}
                        </div>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ── Step 5: Dados do cliente ──────────────────────────────────────── */}
        {step === "customer" && (
          <div>
            <StepHeader
              title="Seus dados"
              subtitle="Para finalizar o agendamento"
              onBack={() => setStep("time")}
            />

            {/* Resumo do agendamento */}
            {selectedService && selectedSlot && (
              <div
                className="rounded-xl p-4 mb-6"
                style={{
                  background: "var(--book-card)",
                  border: "1px solid var(--book-border)",
                  borderLeft: "3px solid var(--book-primary)",
                }}
              >
                <div className="font-semibold mb-2" style={{ color: "var(--book-text)" }}>
                  {selectedService.name}
                </div>
                <div className="text-sm space-y-1" style={{ color: "var(--book-text-secondary)" }}>
                  <div>📅 {fmtDate(selectedSlot.start_at)}</div>
                  <div>👤 {selectedSlot.professional_name}</div>
                </div>
                <div
                  className="text-sm font-semibold mt-3 pt-3"
                  style={{
                    color: "var(--book-primary)",
                    borderTop: "1px solid var(--book-border)",
                  }}
                >
                  {formatBRL(selectedService.price)} · {selectedService.duration_minutes} min
                </div>
              </div>
            )}

            <form onSubmit={handleBook} className="space-y-4">
              {[
                { label: "Nome completo *", type: "text", value: customerName, onChange: setCustomerName, placeholder: "Seu nome", required: true, minLength: 2 },
                { label: "WhatsApp / Telefone *", type: "tel", value: customerPhone, onChange: setCustomerPhone, placeholder: "(11) 99999-9999", required: true },
                { label: "E-mail (opcional)", type: "email", value: customerEmail, onChange: setCustomerEmail, placeholder: "seu@email.com", required: false },
              ].map(({ label, type, value, onChange, placeholder, required, minLength }) => (
                <div key={label}>
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
                      e.currentTarget.style.boxShadow = "0 0 0 2px color-mix(in srgb, var(--book-primary) 20%, transparent)"
                    }}
                    onBlur={(e) => {
                      e.currentTarget.style.borderColor = "var(--book-border)"
                      e.currentTarget.style.boxShadow = "none"
                    }}
                  />
                </div>
              ))}

              {bookingError && (
                <div
                  className="rounded-lg p-3 text-sm"
                  style={{
                    background: "color-mix(in srgb, #ef4444 10%, var(--book-card))",
                    border: "1px solid color-mix(in srgb, #ef4444 40%, transparent)",
                    color: "#fca5a5",
                  }}
                >
                  {bookingError}
                </div>
              )}

              <button
                type="submit"
                disabled={booking}
                className="book-btn-primary w-full py-3 text-sm mt-2"
              >
                {booking ? "Confirmando…" : "Confirmar agendamento"}
              </button>
            </form>
          </div>
        )}

        {/* ── Step 6: Confirmação ───────────────────────────────────────────── */}
        {step === "confirmed" && confirmation && (
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
                  <span className="font-medium text-right" style={{ color: "var(--book-text)" }}>{value}</span>
                </div>
              ))}

              <div
                className="flex justify-between text-sm pt-3 book-divider"
                style={{ borderTop: "1px solid color-mix(in srgb, var(--book-primary) 20%, transparent)" }}
              >
                <span style={{ color: "var(--book-text-muted)" }}>Total</span>
                <span className="font-bold" style={{ color: "var(--book-primary)" }}>
                  {formatBRL(confirmation.total_amount)}
                </span>
              </div>
            </div>

            <p className="text-xs mb-6" style={{ color: "var(--book-text-muted)" }}>
              Código de confirmação:{" "}
              <span className="font-mono" style={{ color: "var(--book-text-secondary)" }}>
                {confirmation.token.slice(0, 8).toUpperCase()}
              </span>
            </p>

            <button
              onClick={() => {
                setStep("service")
                setSelectedService(null)
                setSelectedProfessional(null)
                setSelectedDate("")
                setSelectedSlot(null)
                setConfirmation(null)
                setCustomerName("")
                setCustomerPhone("")
                setCustomerEmail("")
              }}
              className="text-sm underline"
              style={{ color: "var(--book-primary)" }}
            >
              Fazer outro agendamento
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
