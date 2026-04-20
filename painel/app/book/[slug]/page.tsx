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

function fmtDateLabel(d: Date): string {
  return d.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "2-digit" })
}

// ─── Step components ──────────────────────────────────────────────────────────

function StepHeader({ title, subtitle, onBack }: { title: string; subtitle?: string; onBack?: () => void }) {
  return (
    <div className="mb-6">
      {onBack && (
        <button onClick={onBack} className="text-sm text-gray-500 hover:text-gray-800 mb-3 flex items-center gap-1">
          ← Voltar
        </button>
      )}
      <h2 className="text-xl font-bold text-gray-800">{title}</h2>
      {subtitle && <p className="text-sm text-gray-500 mt-1">{subtitle}</p>}
    </div>
  )
}

function Card({ children, onClick, selected }: { children: React.ReactNode; onClick?: () => void; selected?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`w-full text-left rounded-xl border p-4 transition-all duration-150 ${
        selected
          ? "border-indigo-600 bg-indigo-50 ring-2 ring-indigo-300"
          : "border-gray-200 bg-white hover:border-indigo-400 hover:shadow-sm"
      }`}
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

  // Date navigation
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const [dateOffset, setDateOffset] = useState(0)  // days from today shown as the "week start"
  const DATES_SHOWN = 7

  const visibleDates = Array.from({ length: DATES_SHOWN }, (_, i) =>
    addDays(today, dateOffset + i)
  )

  // ── Load company ────────────────────────────────────────────────────────────
  useEffect(() => {
    apiFetch<CompanyInfo>(`/public/${slug}/info`)
      .then(setCompany)
      .catch((e) => setCompanyError(e.message))
  }, [slug])

  // ── Load services ───────────────────────────────────────────────────────────
  useEffect(() => {
    if (!company) return
    setLoadingServices(true)
    apiFetch<ServiceInfo[]>(`/public/${slug}/services`)
      .then(setServices)
      .catch(() => {})
      .finally(() => setLoadingServices(false))
  }, [company, slug])

  // ── Load professionals when service selected ────────────────────────────────
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

  // ── Load slots ──────────────────────────────────────────────────────────────
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

  // ── Step handlers ────────────────────────────────────────────────────────────

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

    // Resolve professional_id: use slot's professional (already resolved for "any")
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
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center max-w-sm px-6">
          <div className="text-4xl mb-4">😕</div>
          <h1 className="text-xl font-bold text-gray-800 mb-2">Página não encontrada</h1>
          <p className="text-sm text-gray-500">{companyError}</p>
        </div>
      </div>
    )
  }

  if (!company) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <p className="text-gray-400 text-sm">Carregando…</p>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b shadow-sm">
        <div className="max-w-lg mx-auto px-6 py-4">
          <h1 className="text-lg font-bold text-gray-900">{company.name}</h1>
          <p className="text-sm text-gray-500">Agendamento online</p>
        </div>
      </div>

      {/* Progress indicator */}
      {step !== "confirmed" && (
        <div className="max-w-lg mx-auto px-6 pt-4">
          <div className="flex gap-1">
            {(["service", "professional", "date", "time", "customer"] as Step[]).map((s, i) => (
              <div
                key={s}
                className={`h-1 flex-1 rounded-full transition-colors ${
                  ["service", "professional", "date", "time", "customer"].indexOf(step) >= i
                    ? "bg-indigo-600"
                    : "bg-gray-200"
                }`}
              />
            ))}
          </div>
        </div>
      )}

      <div className="max-w-lg mx-auto px-6 py-6">

        {/* ── Step 1: Serviço ──────────────────────────────────────────────── */}
        {step === "service" && (
          <div>
            <StepHeader title="Qual serviço você quer agendar?" />
            {loadingServices ? (
              <p className="text-sm text-gray-400">Carregando serviços…</p>
            ) : (
              <div className="space-y-3">
                {services.map((svc) => (
                  <Card key={svc.id} onClick={() => handleSelectService(svc)}>
                    <div className="flex gap-3 items-center">
                      {svc.image_url ? (
                        <img src={svc.image_url} alt={svc.name} className="h-12 w-12 rounded-lg object-cover shrink-0" />
                      ) : (
                        <div className="h-12 w-12 rounded-lg bg-indigo-100 flex items-center justify-center text-indigo-600 text-xl shrink-0">
                          ✂️
                        </div>
                      )}
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-gray-800">{svc.name}</div>
                        {svc.description && (
                          <div className="text-xs text-gray-500 mt-0.5 truncate">{svc.description}</div>
                        )}
                      </div>
                      <div className="text-right shrink-0">
                        <div className="text-sm font-semibold text-indigo-700">{formatBRL(svc.price)}</div>
                        <div className="text-xs text-gray-400">{svc.duration_minutes} min</div>
                      </div>
                    </div>
                  </Card>
                ))}
                {services.length === 0 && (
                  <p className="text-sm text-gray-400 text-center py-8">
                    Nenhum serviço disponível no momento.
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {/* ── Step 2: Profissional ─────────────────────────────────────────── */}
        {step === "professional" && (
          <div>
            <StepHeader
              title="Com quem você prefere?"
              subtitle={selectedService?.name}
              onBack={() => setStep("service")}
            />
            {loadingProfs ? (
              <p className="text-sm text-gray-400">Carregando…</p>
            ) : (
              <div className="space-y-3">
                {professionals.map((prof, i) => (
                  <Card key={prof.id ?? `any-${i}`} onClick={() => handleSelectProfessional(prof)}>
                    <div className="flex items-center gap-3">
                      <div className="h-10 w-10 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-700 font-bold text-sm shrink-0">
                        {prof.name[0]}
                      </div>
                      <span className="font-medium text-gray-800">{prof.name}</span>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Step 3: Data ─────────────────────────────────────────────────── */}
        {step === "date" && (
          <div>
            <StepHeader
              title="Qual dia funciona para você?"
              subtitle={`${selectedService?.name} · ${selectedProfessional?.name}`}
              onBack={() => setStep("professional")}
            />

            {/* Date strip */}
            <div className="flex gap-2 overflow-x-auto pb-2 mb-4">
              {visibleDates.map((d) => {
                const iso = isoDate(d)
                const isSelected = iso === selectedDate
                const isToday = iso === isoDate(today)
                return (
                  <button
                    key={iso}
                    onClick={() => handleSelectDate(d)}
                    className={`flex flex-col items-center rounded-xl px-3 py-2 min-w-[60px] border transition-all ${
                      isSelected
                        ? "bg-indigo-600 border-indigo-600 text-white"
                        : "bg-white border-gray-200 text-gray-700 hover:border-indigo-400"
                    }`}
                  >
                    <span className="text-xs font-medium uppercase">
                      {d.toLocaleDateString("pt-BR", { weekday: "short" })}
                    </span>
                    <span className="text-lg font-bold leading-tight">{d.getDate()}</span>
                    <span className="text-xs">{d.toLocaleDateString("pt-BR", { month: "short" })}</span>
                    {isToday && <span className="text-[10px] mt-0.5 opacity-80">hoje</span>}
                  </button>
                )
              })}
            </div>

            {/* Navigation */}
            <div className="flex justify-between text-sm">
              <button
                onClick={() => setDateOffset((o) => Math.max(0, o - DATES_SHOWN))}
                disabled={dateOffset === 0}
                className="text-indigo-600 disabled:opacity-30"
              >
                ← Anterior
              </button>
              <button
                onClick={() => setDateOffset((o) => o + DATES_SHOWN)}
                className="text-indigo-600"
              >
                Próximos →
              </button>
            </div>

            {selectedDate && (
              <div className="mt-4 text-center">
                <button
                  onClick={() => setStep("time")}
                  className="bg-indigo-600 text-white px-6 py-2 rounded-lg text-sm font-medium hover:bg-indigo-700"
                >
                  Ver horários disponíveis →
                </button>
              </div>
            )}
          </div>
        )}

        {/* ── Step 4: Horário ──────────────────────────────────────────────── */}
        {step === "time" && (
          <div>
            <StepHeader
              title="Escolha um horário"
              subtitle={selectedDate
                ? new Date(selectedDate + "T12:00:00").toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long" })
                : ""}
              onBack={() => setStep("date")}
            />
            {loadingSlots ? (
              <p className="text-sm text-gray-400">Buscando horários…</p>
            ) : slots.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-3">Nenhum horário disponível neste dia.</p>
                <button onClick={() => setStep("date")} className="text-indigo-600 text-sm underline">
                  Escolher outra data
                </button>
              </div>
            ) : (
              <div className="grid grid-cols-3 gap-2">
                {slots.map((slot, i) => {
                  const time = new Date(slot.start_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
                  return (
                    <button
                      key={i}
                      onClick={() => handleSelectSlot(slot)}
                      className="rounded-xl border border-gray-200 bg-white py-3 text-sm font-medium text-gray-800 hover:border-indigo-500 hover:bg-indigo-50 hover:text-indigo-700 transition-colors"
                    >
                      {time}
                      {!selectedProfessional?.id && (
                        <div className="text-xs text-gray-400 truncate px-1">{slot.professional_name}</div>
                      )}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        )}

        {/* ── Step 5: Dados do cliente ─────────────────────────────────────── */}
        {step === "customer" && (
          <div>
            <StepHeader
              title="Seus dados"
              subtitle="Para finalizar o agendamento"
              onBack={() => setStep("time")}
            />

            {/* Summary card */}
            {selectedService && selectedSlot && (
              <div className="bg-indigo-50 rounded-xl p-4 mb-6 text-sm">
                <div className="font-semibold text-indigo-800 mb-1">{selectedService.name}</div>
                <div className="text-indigo-600">
                  📅 {fmtDate(selectedSlot.start_at)}
                </div>
                <div className="text-indigo-600">
                  👤 {selectedSlot.professional_name}
                </div>
                <div className="text-indigo-700 font-medium mt-1">
                  {formatBRL(selectedService.price)} · {selectedService.duration_minutes} min
                </div>
              </div>
            )}

            <form onSubmit={handleBook} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Nome completo *
                </label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  required
                  minLength={2}
                  placeholder="Seu nome"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  WhatsApp / Telefone *
                </label>
                <input
                  type="tel"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                  required
                  placeholder="(11) 99999-9999"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  E-mail (opcional)
                </label>
                <input
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder="seu@email.com"
                  className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
                />
              </div>

              {bookingError && (
                <div className="rounded-lg bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                  {bookingError}
                </div>
              )}

              <button
                type="submit"
                disabled={booking}
                className="w-full bg-indigo-600 text-white py-3 rounded-xl font-semibold text-sm hover:bg-indigo-700 disabled:opacity-60 transition-colors mt-2"
              >
                {booking ? "Confirmando…" : "Confirmar agendamento"}
              </button>
            </form>
          </div>
        )}

        {/* ── Step 6: Confirmação ──────────────────────────────────────────── */}
        {step === "confirmed" && confirmation && (
          <div className="text-center py-6">
            <div className="text-5xl mb-4">✅</div>
            <h2 className="text-2xl font-bold text-gray-800 mb-2">Agendado!</h2>
            <p className="text-gray-500 mb-6">Seu horário está confirmado.</p>

            <div className="bg-white rounded-2xl border shadow-sm p-6 text-left space-y-3 mb-6">
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Serviço</span>
                <span className="font-medium text-gray-800">{confirmation.service_name}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Profissional</span>
                <span className="font-medium text-gray-800">{confirmation.professional_name}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-gray-500">Data e hora</span>
                <span className="font-medium text-gray-800 text-right">{fmtDate(confirmation.start_at)}</span>
              </div>
              <div className="flex justify-between text-sm border-t pt-3">
                <span className="text-gray-500">Total</span>
                <span className="font-bold text-indigo-700">{formatBRL(confirmation.total_amount)}</span>
              </div>
            </div>

            <p className="text-xs text-gray-400 mb-6">
              Código de confirmação: <span className="font-mono">{confirmation.token.slice(0, 8).toUpperCase()}</span>
            </p>

            <button
              onClick={() => {
                setStep("service")
                setSelectedService(null)
                setSelectedProfessional(null)
                setSelectedDate("")
                setSelectedSlot(null)
                setConfirmation(null)
                setCustomerName(""); setCustomerPhone(""); setCustomerEmail("")
              }}
              className="text-indigo-600 text-sm underline"
            >
              Fazer outro agendamento
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
