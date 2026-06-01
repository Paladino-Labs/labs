"use client"

import { Suspense, useEffect, useState, useMemo } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import type { Professional, Service, Customer } from "@/types"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"

interface AvailableSlot {
  start_at: string
  end_at: string
  professional_id: string
  professional_name: string
}

// ── Modos do campo cliente ────────────────────────────────────────────────────
type ClientMode = "search" | "new"

function todayString(): string {
  const d = new Date()
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

export default function NewAppointmentPage() {
  return (
    <Suspense>
      <NewAppointmentContent />
    </Suspense>
  )
}

function NewAppointmentContent() {
  const router       = useRouter()
  const searchParams = useSearchParams()

  // ── Dados do formulário principal ─────────────────────────────────────────
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [services,      setServices]      = useState<Service[]>([])
  const [customers,     setCustomers]     = useState<Customer[]>([])

  const [professionalId, setProfessionalId] = useState(searchParams.get("professional_id") ?? "")
  const [serviceId,      setServiceId]      = useState("")
  const [selectedDate,   setSelectedDate]   = useState(() => {
    // Pré-preenche com a data do slot clicado no calendário
    const raw = searchParams.get("start_at")
    if (!raw) return todayString()
    const d = new Date(raw)
    const pad = (n: number) => String(n).padStart(2, "0")
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
  })
  const [startAt,        setStartAt]        = useState("")
  const [endAt,          setEndAt]          = useState("")

  // ── Slots ─────────────────────────────────────────────────────────────────
  const [slots,         setSlots]        = useState<AvailableSlot[]>([])
  const [loadingSlots,  setLoadingSlots] = useState(false)
  const [selectedSlot,  setSelectedSlot] = useState<AvailableSlot | null>(null)

  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState<string | null>(null)

  // ── Modo do campo cliente: buscar existente ou cadastrar novo ─────────────
  const [clientMode,    setClientMode]    = useState<ClientMode>("search")
  const [clientSearch,  setClientSearch]  = useState("")
  const [clientId,      setClientId]      = useState("")
  const [newName,       setNewName]       = useState("")
  const [newPhone,      setNewPhone]      = useState("")
  const [newEmail,      setNewEmail]      = useState("")
  const [creatingClient, setCreatingClient] = useState(false)
  const [clientError,   setClientError]   = useState<string | null>(null)

  // ── Fetch inicial ──────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      api.get<Professional[]>("/professionals/"),
      api.get<Service[]>("/services/"),
      api.get<Customer[]>("/customers/"),
    ]).then(([p, s, c]) => {
      setProfessionals(p)
      setServices(s)
      setCustomers(c)
    }).catch(() => setError("Erro ao carregar dados. Recarregue a página."))
  }, [])

  // ── Buscar slots quando profissional + serviço + data estão selecionados ──
  useEffect(() => {
    if (!professionalId || !serviceId || !selectedDate) {
      setSlots([])
      setSelectedSlot(null)
      setStartAt("")
      setEndAt("")
      return
    }

    setLoadingSlots(true)
    setSlots([])
    setSelectedSlot(null)
    setStartAt("")
    setEndAt("")

    api.get<AvailableSlot[]>(
      `/availability/slots?professional_id=${professionalId}&service_id=${serviceId}&date=${selectedDate}`
    )
      .then(setSlots)
      .catch(() => setSlots([]))
      .finally(() => setLoadingSlots(false))
  }, [professionalId, serviceId, selectedDate])

  // ── Filtro de clientes por busca ───────────────────────────────────────────
  const filteredCustomers = useMemo(() => {
    const q = clientSearch.trim().toLowerCase()
    if (!q) return customers
    return customers.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        (c.phone ?? "").includes(q)
    )
  }, [customers, clientSearch])

  // ── Selecionar slot ───────────────────────────────────────────────────────
  function handleSelectSlot(slot: AvailableSlot) {
    setSelectedSlot(slot)
    setStartAt(slot.start_at)
    setEndAt(slot.end_at)
    // Se o profissional ainda não foi fixado e o slot tem profissional, mantém o selecionado
  }

  // ── Cadastrar novo cliente inline ─────────────────────────────────────────
  async function handleCreateClient() {
    if (newName.trim().length < 2) {
      setClientError("Nome deve ter pelo menos 2 caracteres.")
      return
    }
    if ((newPhone.replace(/\D/g, "")).length < 10) {
      setClientError("Telefone inválido.")
      return
    }
    setClientError(null)
    setCreatingClient(true)
    try {
      const created = await api.post<Customer>("/customers/", {
        name:  newName.trim(),
        phone: newPhone.trim(),
        email: newEmail.trim() || undefined,
      })
      setCustomers((prev) => [...prev, created])
      setClientId(created.id)
      setClientMode("search")
      setClientSearch(created.name)
      setNewName("")
      setNewPhone("")
      setNewEmail("")
    } catch (err: unknown) {
      setClientError((err as Error).message ?? "Erro ao cadastrar cliente.")
    } finally {
      setCreatingClient(false)
    }
  }

  // ── Submeter agendamento ──────────────────────────────────────────────────
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!clientId) {
      setError("Selecione ou cadastre um cliente.")
      return
    }
    if (!startAt) {
      setError("Selecione um horário disponível.")
      return
    }
    setError(null)
    setLoading(true)
    try {
      await api.post("/appointments/", {
        client_id:       clientId,
        professional_id: professionalId,
        services:        [{ service_id: serviceId }],
        start_at:        startAt,
        idempotency_key: crypto.randomUUID(),
      })
      router.replace("/dashboard")
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao criar agendamento.")
    } finally {
      setLoading(false)
    }
  }

  const selectedCustomer = customers.find((c) => c.id === clientId)

  const canFetchSlots = Boolean(professionalId && serviceId && selectedDate)

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-lg mx-auto">
      <h1 className="font-display text-2xl mb-6">Novo Agendamento</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dados do agendamento</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-5">

            {/* ── Profissional ──────────────────────────────────────────────── */}
            <div className="space-y-1.5">
              <Label>Profissional</Label>
              <Select value={professionalId} onValueChange={(v) => {
                if (v) { setProfessionalId(v); setSelectedSlot(null); setStartAt("") }
              }}>
                <SelectTrigger>
                  <span className={professionalId ? "text-foreground" : "text-muted-foreground"}>
                    {professionals.find((p) => p.id === professionalId)?.name ?? "Selecione o profissional"}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {professionals.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* ── Serviço ───────────────────────────────────────────────────── */}
            <div className="space-y-1.5">
              <Label>Serviço</Label>
              <Select value={serviceId} onValueChange={(v) => {
                if (v) { setServiceId(v); setSelectedSlot(null); setStartAt("") }
              }}>
                <SelectTrigger>
                  <span className={serviceId ? "text-foreground" : "text-muted-foreground"}>
                    {(() => {
                      const s = services.find((s) => s.id === serviceId)
                      return s ? `${s.name} — ${formatBRL(s.price)} / ${s.duration}min` : "Selecione o serviço"
                    })()}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {services.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.name} — {formatBRL(s.price)} / {s.duration}min
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* ── Data ──────────────────────────────────────────────────────── */}
            <div className="space-y-1.5">
              <Label htmlFor="date">Data</Label>
              <Input
                id="date"
                type="date"
                value={selectedDate}
                min={todayString()}
                onChange={(e) => {
                  setSelectedDate(e.target.value)
                  setSelectedSlot(null)
                  setStartAt("")
                }}
                required
              />
            </div>

            {/* ── Horários disponíveis ──────────────────────────────────────── */}
            {canFetchSlots && (
              <div className="space-y-1.5">
                <Label>Horário disponível</Label>
                {loadingSlots ? (
                  <p className="text-sm text-muted-foreground">Buscando horários…</p>
                ) : slots.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    Nenhum horário disponível para esta data. Tente outro dia.
                  </p>
                ) : (
                  <div className="flex flex-wrap gap-2">
                    {slots.map((slot) => {
                      const t = new Date(slot.start_at)
                      const pad = (n: number) => String(n).padStart(2, "0")
                      const label = `${pad(t.getHours())}:${pad(t.getMinutes())}`
                      const selected = selectedSlot?.start_at === slot.start_at &&
                                       selectedSlot?.professional_id === slot.professional_id
                      return (
                        <button
                          key={`${slot.start_at}-${slot.professional_id}`}
                          type="button"
                          onClick={() => handleSelectSlot(slot)}
                          className={
                            selected
                              ? "rounded-md border-2 border-primary bg-primary/10 px-4 py-2 font-mono text-sm font-medium transition-all"
                              : "rounded-md border border-border px-4 py-2 font-mono text-sm hover:border-primary hover:bg-primary/5 transition-all"
                          }
                        >
                          {label}
                        </button>
                      )
                    })}
                  </div>
                )}
                {selectedSlot && (
                  <p className="text-xs text-muted-foreground">
                    Horário selecionado: {new Date(selectedSlot.start_at).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
                    {" — "}
                    {selectedSlot.professional_name}
                  </p>
                )}
              </div>
            )}

            {/* ── Cliente ───────────────────────────────────────────────────── */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label>Cliente</Label>
                {clientMode === "search" ? (
                  <button
                    type="button"
                    onClick={() => { setClientMode("new"); setClientError(null) }}
                    className="text-xs text-primary font-medium hover:underline"
                  >
                    + Novo cliente
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => { setClientMode("search"); setClientError(null) }}
                    className="text-xs text-muted-foreground hover:underline"
                  >
                    ← Buscar existente
                  </button>
                )}
              </div>

              {clientMode === "search" && (
                <div className="space-y-2">
                  <Input
                    placeholder="Buscar por nome ou telefone…"
                    value={clientSearch}
                    onChange={(e) => {
                      setClientSearch(e.target.value)
                      if (clientId) setClientId("")
                    }}
                  />

                  {clientSearch && !clientId && (
                    <div className="border rounded-lg overflow-hidden divide-y max-h-44 overflow-y-auto">
                      {filteredCustomers.length === 0 ? (
                        <div className="px-3 py-2.5 text-sm text-muted-foreground">
                          Nenhum cliente encontrado.{" "}
                          <button
                            type="button"
                            onClick={() => { setClientMode("new"); setNewName(clientSearch) }}
                            className="text-primary font-medium hover:underline"
                          >
                            Cadastrar "{clientSearch}"
                          </button>
                        </div>
                      ) : (
                        filteredCustomers.map((c) => (
                          <button
                            key={c.id}
                            type="button"
                            onClick={() => {
                              setClientId(c.id)
                              setClientSearch(c.name)
                            }}
                            className="w-full text-left px-3 py-2.5 text-sm hover:bg-muted transition-colors"
                          >
                            <span className="font-medium">{c.name}</span>
                            <span className="text-muted-foreground ml-2">{c.phone}</span>
                          </button>
                        ))
                      )}
                    </div>
                  )}

                  {selectedCustomer && (
                    <div className="flex items-center justify-between rounded-lg border bg-muted/40 px-3 py-2.5 text-sm">
                      <div>
                        <span className="font-medium">{selectedCustomer.name}</span>
                        <span className="text-muted-foreground ml-2">{selectedCustomer.phone}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => { setClientId(""); setClientSearch("") }}
                        className="text-muted-foreground hover:text-foreground ml-2"
                      >
                        ×
                      </button>
                    </div>
                  )}
                </div>
              )}

              {clientMode === "new" && (
                <div className="rounded-lg border bg-muted/30 p-4 space-y-3">
                  <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                    Novo cliente
                  </p>

                  <div className="space-y-1.5">
                    <Label htmlFor="new-name">Nome *</Label>
                    <Input
                      id="new-name"
                      placeholder="Nome completo"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      minLength={2}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="new-phone">Telefone / WhatsApp *</Label>
                    <Input
                      id="new-phone"
                      type="tel"
                      placeholder="(11) 99999-9999"
                      value={newPhone}
                      onChange={(e) => setNewPhone(e.target.value)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <Label htmlFor="new-email">E-mail <span className="text-muted-foreground font-normal">(opcional)</span></Label>
                    <Input
                      id="new-email"
                      type="email"
                      placeholder="email@exemplo.com"
                      value={newEmail}
                      onChange={(e) => setNewEmail(e.target.value)}
                    />
                  </div>

                  {clientError && (
                    <p className="text-xs text-destructive">{clientError}</p>
                  )}

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-full"
                    onClick={handleCreateClient}
                    disabled={creatingClient}
                  >
                    {creatingClient ? "Cadastrando…" : "Cadastrar e selecionar"}
                  </Button>
                </div>
              )}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            {/* ── Ações ────────────────────────────────────────────────────── */}
            <div className="flex gap-3 pt-1">
              <Button type="button" variant="outline" className="flex-1" onClick={() => router.back()}>
                Voltar
              </Button>
              <Button
                type="submit"
                className="flex-1"
                disabled={loading || !professionalId || !serviceId || !clientId || !startAt}
              >
                {loading ? "Agendando…" : "Confirmar"}
              </Button>
            </div>

          </form>
        </CardContent>
      </Card>
    </div>
  )
}
