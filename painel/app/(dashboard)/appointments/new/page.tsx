"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
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

export default function NewAppointmentPage() {
  const router = useRouter()

  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [customers, setCustomers] = useState<Customer[]>([])

  const [professionalId, setProfessionalId] = useState("")
  const [serviceId, setServiceId] = useState("")
  const [clientId, setClientId] = useState("")
  const [startAt, setStartAt] = useState("")

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await api.post("/appointments/", {
        client_id: clientId,
        professional_id: professionalId,
        services: [{ service_id: serviceId }],
        start_at: new Date(startAt).toISOString(),
        idempotency_key: crypto.randomUUID(),
      })
      router.replace("/dashboard")
    } catch (err: unknown) {
      setError((err as Error).message ?? "Erro ao criar agendamento.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-lg mx-auto">
      <h1 className="text-2xl font-bold mb-6">Novo Agendamento</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dados do agendamento</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Profissional */}
            <div className="space-y-1">
              <Label>Profissional</Label>
              <Select value={professionalId} onValueChange={(v) => v && setProfessionalId(v)} required>
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

            {/* Serviço */}
            <div className="space-y-1">
              <Label>Serviço</Label>
              <Select value={serviceId} onValueChange={(v) => v && setServiceId(v)} required>
                <SelectTrigger>
                  <span className={serviceId ? "text-foreground" : "text-muted-foreground"}>
                    {(() => {
                      const s = services.find((s) => s.id === serviceId)
                      return s
                        ? `${s.name} — ${formatBRL(s.price)} / ${s.duration}min`
                        : "Selecione o serviço"
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

            {/* Cliente */}
            <div className="space-y-1">
              <Label>Cliente</Label>
              <Select value={clientId} onValueChange={(v) => v && setClientId(v)} required>
                <SelectTrigger>
                  <span className={clientId ? "text-foreground" : "text-muted-foreground"}>
                    {(() => {
                      const c = customers.find((c) => c.id === clientId)
                      return c ? `${c.name} · ${c.phone}` : "Selecione o cliente"
                    })()}
                  </span>
                </SelectTrigger>
                <SelectContent>
                  {customers.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} · {c.phone}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Horário */}
            <div className="space-y-1">
              <Label htmlFor="start-at">Horário de início</Label>
              <Input
                id="start-at"
                type="datetime-local"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                required
              />
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex gap-3 pt-2">
              <Button
                type="button"
                variant="outline"
                className="flex-1"
                onClick={() => router.back()}
              >
                Voltar
              </Button>
              <Button type="submit" className="flex-1" disabled={loading}>
                {loading ? "Agendando…" : "Confirmar"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
