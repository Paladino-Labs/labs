"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import type { Customer, CustomerAppointmentItem } from "@/types"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Badge } from "@/components/ui/badge"
import {
  Card, CardContent, CardHeader, CardTitle,
} from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"

const STATUS_LABELS: Record<string, string> = {
  SCHEDULED:   "Agendado",
  IN_PROGRESS: "Em andamento",
  COMPLETED:   "Concluído",
  CANCELLED:   "Cancelado",
  NO_SHOW:     "Não compareceu",
}

const STATUS_VARIANT: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  SCHEDULED:   "default",
  IN_PROGRESS: "secondary",
  COMPLETED:   "outline",
  CANCELLED:   "destructive",
  NO_SHOW:     "destructive",
}

function fmtDt(iso: string) {
  return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
}

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [customer, setCustomer] = useState<Customer | null>(null)
  const [appointments, setAppointments] = useState<CustomerAppointmentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Edit state
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [email, setEmail] = useState("")
  const [notes, setNotes] = useState("")

  const fetchAll = useCallback(async () => {
    try {
      const [c, appts] = await Promise.all([
        api.get<Customer>(`/customers/${id}`),
        api.get<CustomerAppointmentItem[]>(`/customers/${id}/appointments`),
      ])
      setCustomer(c)
      setAppointments(appts)
      setName(c.name)
      setPhone(c.phone)
      setEmail(c.email ?? "")
      setNotes(c.notes ?? "")
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { fetchAll() }, [fetchAll])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.patch(`/customers/${id}`, {
        name,
        phone,
        email: email || null,
        notes: notes || null,
      })
      setEditing(false)
      fetchAll()
    } catch (err: unknown) {
      alert((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <p className="text-muted-foreground p-6">Carregando…</p>
  if (error || !customer) return (
    <div className="p-6">
      <p className="text-destructive">{error ?? "Cliente não encontrado."}</p>
      <Button variant="outline" className="mt-4" onClick={() => router.back()}>Voltar</Button>
    </div>
  )

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-4">
        <Button variant="outline" size="sm" onClick={() => router.back()}>← Voltar</Button>
        <h1 className="text-2xl font-bold">{customer.name}</h1>
        <ActiveBadge active={customer.active} />
      </div>

      {/* Info Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle>Informações</CardTitle>
          {!editing && (
            <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Editar</Button>
          )}
        </CardHeader>
        <CardContent>
          {editing ? (
            <form onSubmit={handleSave} className="space-y-4 max-w-lg">
              <div className="space-y-1">
                <Label htmlFor="cd-name">Nome *</Label>
                <Input id="cd-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cd-phone">Telefone *</Label>
                <Input id="cd-phone" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cd-email">E-mail</Label>
                <Input id="cd-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cd-notes">Observações</Label>
                <textarea
                  id="cd-notes"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={4}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                  placeholder="Preferências, alergias, observações…"
                />
              </div>
              <div className="flex gap-2">
                <Button type="submit" disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
                <Button type="button" variant="outline" onClick={() => setEditing(false)}>Cancelar</Button>
              </div>
            </form>
          ) : (
            <dl className="grid grid-cols-2 gap-x-8 gap-y-3 text-sm max-w-lg">
              <dt className="text-muted-foreground">Telefone</dt>
              <dd>{customer.phone}</dd>
              <dt className="text-muted-foreground">E-mail</dt>
              <dd>{customer.email ?? "—"}</dd>
              {customer.notes && (
                <>
                  <dt className="text-muted-foreground">Observações</dt>
                  <dd className="whitespace-pre-wrap">{customer.notes}</dd>
                </>
              )}
            </dl>
          )}
        </CardContent>
      </Card>

      {/* Appointment History */}
      <Card>
        <CardHeader>
          <CardTitle>Histórico de Agendamentos ({appointments.length})</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Data / Hora</TableHead>
                <TableHead>Serviços</TableHead>
                <TableHead>Profissional</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Total</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {appointments.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    Nenhum agendamento encontrado.
                  </TableCell>
                </TableRow>
              )}
              {appointments.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="text-sm">
                    <div>{fmtDt(a.start_at)}</div>
                    <div className="text-xs text-muted-foreground">{fmtDt(a.end_at)}</div>
                  </TableCell>
                  <TableCell className="text-sm">{a.service_names.join(", ")}</TableCell>
                  <TableCell className="text-sm">{a.professional_name ?? "—"}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[a.status] ?? "secondary"}>
                      {STATUS_LABELS[a.status] ?? a.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right text-sm font-medium">
                    {formatBRL(a.total_amount)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
