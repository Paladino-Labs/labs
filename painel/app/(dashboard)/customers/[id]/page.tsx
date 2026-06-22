"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, AlertTriangle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { Customer, CustomerAppointmentItem } from "@/types"
import { formatBRL, formatDateTime } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { AppointmentBadge, CrmBadge } from "@/components/FsmBadge"
import { CUSTOMER_CREDIT_STATUS_LABELS } from "@/lib/constants"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

interface ClassificationOut {
  id: string
  customer_id: string
  classification: string
  computed_at: string
  metrics_snapshot: Record<string, unknown>
}
interface ClassificationResponse {
  current: ClassificationOut | null
  history: ClassificationOut[]
}
interface Suggestion { type: string; reason: string }
interface Insights {
  churn_risk: string
  estimated_return_window?: string | null
  classification?: string | null
  metrics: Record<string, unknown>
  suggestions: Suggestion[]
}
interface CustomerCredit {
  credit_id:        string
  customer_id:      string
  entitlement_type: string
  source_id?:       string | null
  service_id?:      string | null
  service_name?:    string | null
  product_id?:      string | null
  product_name?:    string | null
  total_cotas:      number
  remaining_cotas:  number
  status:           string
  granted_at:       string
  expires_at?:      string | null
}
interface ConsentRecord {
  id: string
  consent_type: string
  channel?: string | null
  status: string
  source_channel: string
  occurred_at: string
  notes?: string | null
}

const CONSENT_TYPES = ["COMMUNICATION", "DATA_PROCESSING", "PAYMENT_STORAGE", "MARKETING"] as const
const CONSENT_LABELS: Record<string, string> = {
  COMMUNICATION: "Comunicação",
  DATA_PROCESSING: "Tratamento de dados",
  PAYMENT_STORAGE: "Armazenamento de pagamento",
  MARKETING: "Marketing",
}
const SUGGESTION_LABELS: Record<string, string> = {
  RESCHEDULE: "Sugerir remarcação",
  PACKAGE: "Oferecer pacote",
  PRODUCT: "Recomendar produto",
}
const CHURN_LABELS: Record<string, string> = { LOW: "Baixo", MEDIUM: "Médio", HIGH: "Alto" }
const CREDIT_TYPE_LABELS: Record<string, string> = {
  PACKAGE:      "Pacote",
  SUBSCRIPTION: "Assinatura",
  GRANT_COTA:   "Cota cortesia",
}

export default function CustomerDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()

  const [customer, setCustomer] = useState<Customer | null>(null)
  const [classification, setClassification] = useState<ClassificationResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadHeader = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const c = await api.get<Customer>(`/customers/${id}`)
      setCustomer(c)
      try {
        setClassification(await api.get<ClassificationResponse>(`/customers/${id}/classification`))
      } catch { setClassification(null) }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { loadHeader() }, [loadHeader])

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-72" />
        <Skeleton className="h-8 w-full max-w-md" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (error || !customer) {
    return (
      <div className="space-y-4">
        <Button variant="outline" size="sm" onClick={() => router.back()}>← Voltar</Button>
        <ErrorState message={error ?? "Cliente não encontrado."} onRetry={loadHeader} />
      </div>
    )
  }

  const current = classification?.current?.classification
  const initials = customer.name.split(" ").slice(0, 2).map((p) => p[0]?.toUpperCase()).join("")

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <button onClick={() => router.back()} className="inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft size={16} strokeWidth={1.5} /> Voltar
        </button>
      </div>

      <PageHeader
        eyebrow="Cliente"
        title={customer.name}
        description={customer.phone}
      >
        {current && <CrmBadge classification={current} />}
        <EditCustomerDialog customer={customer} onUpdated={loadHeader} />
      </PageHeader>

      <div className="flex items-center gap-3">
        <div className="h-12 w-12 rounded-full bg-primary/15 text-sm font-medium text-primary flex items-center justify-center select-none">
          {initials}
        </div>
        <div className="text-sm">
          <p>{customer.email ?? "Sem e-mail"}</p>
          <p className="text-muted-foreground">{customer.active ? "Ativo" : "Inativo"}</p>
        </div>
      </div>

      <Tabs defaultValue="summary">
        <TabsList>
          <TabsTrigger value="summary">Resumo</TabsTrigger>
          <TabsTrigger value="history">Histórico</TabsTrigger>
          <TabsTrigger value="quotas">Cotas</TabsTrigger>
          <TabsTrigger value="consents">Consentimentos</TabsTrigger>
        </TabsList>
        <TabsContent value="summary"><SummaryTab id={id} classification={classification} /></TabsContent>
        <TabsContent value="history"><HistoryTab id={id} /></TabsContent>
        <TabsContent value="quotas"><QuotasTab id={id} /></TabsContent>
        <TabsContent value="consents"><ConsentsTab id={id} /></TabsContent>
      </Tabs>
    </div>
  )
}

/* ------------------------------- Resumo ------------------------------- */
function SummaryTab({ id, classification }: { id: string; classification: ClassificationResponse | null }) {
  const [insights, setInsights] = useState<Insights | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setInsights(await api.get<Insights>(`/customers/${id}/insights`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader><CardTitle>Classificação</CardTitle></CardHeader>
        <CardContent>
          {classification?.current ? (
            <div className="flex items-center gap-3 text-sm">
              <CrmBadge classification={classification.current.classification} />
              <span className="text-muted-foreground">
                desde {formatDateTime(classification.current.computed_at)}
              </span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Sem classificação registrada.</p>
          )}
          {classification && classification.history.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {classification.history.slice(1).map((h) => (
                <Badge key={h.id} variant="outline" className="font-normal">
                  {h.classification} · {formatDateTime(h.computed_at)}
                </Badge>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Insights</CardTitle></CardHeader>
        <CardContent>
          {loading ? (
            <Skeleton className="h-24 w-full" />
          ) : error ? (
            <ErrorState message={error} onRetry={load} />
          ) : !insights ? (
            <p className="text-sm text-muted-foreground">Sem insights disponíveis.</p>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm">
                <AlertTriangle size={16} strokeWidth={1.5} className="text-amber-600" />
                <span>Risco de churn:</span>
                <Badge variant={insights.churn_risk === "HIGH" ? "destructive" : "secondary"}>
                  {CHURN_LABELS[insights.churn_risk] ?? insights.churn_risk}
                </Badge>
              </div>
              {insights.suggestions.length > 0 ? (
                <ul className="space-y-2">
                  {insights.suggestions.map((s, i) => (
                    <li key={i} className="rounded-md border border-border bg-card px-3 py-2 text-sm">
                      <p className="font-medium">{SUGGESTION_LABELS[s.type] ?? s.type}</p>
                      <p className="text-xs text-muted-foreground">{s.reason}</p>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Nenhuma sugestão no momento.</p>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

/* ------------------------------- Histórico ------------------------------- */
function HistoryTab({ id }: { id: string }) {
  const [items, setItems] = useState<CustomerAppointmentItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setItems(await api.get<CustomerAppointmentItem[]>(`/customers/${id}/appointments`))
    } catch (err: unknown) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])

  if (loading) return <Skeleton className="h-64 w-full" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (items.length === 0) return <EmptyState title="Nenhum agendamento" description="Este cliente ainda não tem histórico." />

  return (
    <div className="rounded-md border border-border bg-card">
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
          {items.map((a) => (
            <TableRow key={a.id}>
              <TableCell className="text-sm">{formatDateTime(a.start_at)}</TableCell>
              <TableCell className="text-sm">{a.service_names.join(", ")}</TableCell>
              <TableCell className="text-sm">{a.professional_name ?? "—"}</TableCell>
              <TableCell><AppointmentBadge status={a.status} /></TableCell>
              <TableCell className="text-right text-sm font-medium">{formatBRL(a.total_amount)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

/* ------------------------------- Cotas ------------------------------- */
function QuotasTab({ id }: { id: string }) {
  const { role } = useAuth()
  const canManage = role === "OWNER" || role === "ADMIN"
  const [credits, setCredits] = useState<CustomerCredit[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setCredits(await api.get<CustomerCredit[]>(`/customer-credits?customer_id=${id}`))
    } catch (err: unknown) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])

  async function revoke(creditId: string) {
    try {
      await api.post(`/customer-credits/${creditId}/revoke`, { reason: "Revogado pelo painel" })
      toast.success("Cota revogada")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao revogar")
    }
  }

  return (
    <div className="space-y-4">
      {canManage && (
        <div className="flex justify-end">
          <GrantCotaDialog customerId={id} onGranted={load} />
        </div>
      )}
      {loading ? (
        <Skeleton className="h-48 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : credits.length === 0 ? (
        <EmptyState title="Nenhuma cota" description="Este cliente não possui cotas concedidas." />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {credits.map((c) => (
            <Card key={c.credit_id}>
              <CardContent className="space-y-2 pt-6">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="font-medium">
                      {c.service_name ?? c.product_name ?? CREDIT_TYPE_LABELS[c.entitlement_type] ?? c.entitlement_type}
                    </p>
                    {(c.service_name || c.product_name) && (
                      <p className="text-xs text-muted-foreground">
                        {CREDIT_TYPE_LABELS[c.entitlement_type] ?? c.entitlement_type}
                      </p>
                    )}
                  </div>
                  <Badge variant={c.status === "ACTIVE" ? "default" : "outline"}>
                    {CUSTOMER_CREDIT_STATUS_LABELS[c.status] ?? c.status}
                  </Badge>
                </div>
                <p className="text-sm">
                  <span className="font-mono text-base">{c.remaining_cotas}</span>
                  <span className="text-muted-foreground"> / {c.total_cotas} restantes</span>
                </p>
                <p className="text-xs text-muted-foreground">
                  {c.expires_at ? `Válido até ${formatDateTime(c.expires_at)}` : "Sem validade"}
                </p>
                {canManage && c.status === "ACTIVE" && (
                  <Dialog>
                    <DialogTrigger render={<Button size="sm" variant="outline" />}>Revogar</DialogTrigger>
                    <DialogContent>
                      <DialogHeader><DialogTitle>Revogar cota</DialogTitle></DialogHeader>
                      <p className="text-sm text-muted-foreground">
                        Revogar {c.entitlement_type} ({c.remaining_cotas} restantes)?
                      </p>
                      <DialogFooter>
                        <DialogClose render={<Button variant="outline" />}>Cancelar</DialogClose>
                        <DialogClose render={<Button variant="destructive" />} onClick={() => revoke(c.credit_id)}>
                          Revogar
                        </DialogClose>
                      </DialogFooter>
                    </DialogContent>
                  </Dialog>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

function GrantCotaDialog({ customerId, onGranted }: { customerId: string; onGranted: () => void }) {
  const [open, setOpen] = useState(false)
  const [totalCotas, setTotalCotas] = useState("1")
  const [expiresAt, setExpiresAt] = useState("")
  const [reason, setReason] = useState("")
  const [saving, setSaving] = useState(false)

  async function handleGrant() {
    if (!reason.trim()) { toast.error("Informe o motivo."); return }
    if (Number(totalCotas) <= 0) { toast.error("Quantidade deve ser maior que zero."); return }
    setSaving(true)
    try {
      await api.post("/customer-credits/grant-cota", {
        customer_id: customerId,
        total_cotas: Number(totalCotas),
        expires_at: expiresAt ? new Date(expiresAt).toISOString() : undefined,
        reason,
      })
      toast.success("Cota concedida")
      setOpen(false)
      setTotalCotas("1"); setExpiresAt(""); setReason("")
      onGranted()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao conceder cota")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" />}>+ Conceder cota</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Conceder cota</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="gc-total">Quantidade de cotas *</Label>
            <Input id="gc-total" type="number" min={1} value={totalCotas} onChange={(e) => setTotalCotas(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="gc-exp">Validade (opcional)</Label>
            <Input id="gc-exp" type="date" value={expiresAt} onChange={(e) => setExpiresAt(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="gc-reason">Motivo *</Label>
            <Textarea id="gc-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} placeholder="Ex.: cortesia, pacote promocional…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handleGrant} disabled={saving}>{saving ? "Concedendo…" : "Conceder"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------- Consentimentos ------------------------------- */
function ConsentsTab({ id }: { id: string }) {
  const [records, setRecords] = useState<ConsentRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setRecords(await api.get<ConsentRecord[]>(`/customers/${id}/consents`))
    } catch (err: unknown) { setError((err as Error).message) }
    finally { setLoading(false) }
  }, [id])
  useEffect(() => { load() }, [load])

  function statusFor(type: string): string {
    const rec = records.find((r) => r.consent_type === type)
    if (rec) return rec.status
    // COMMUNICATION é opt-out (default GRANTED quando não há registro)
    return type === "COMMUNICATION" ? "GRANTED" : "REVOKED"
  }

  async function change(type: string, action: "grant" | "revoke") {
    setBusy(type)
    try {
      await api.post(`/customers/${id}/consents/${action}`, { consent_type: type })
      toast.success(action === "grant" ? "Consentimento concedido" : "Consentimento revogado")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao atualizar consentimento")
    } finally { setBusy(null) }
  }

  if (loading) return <Skeleton className="h-48 w-full" />
  if (error) return <ErrorState message={error} onRetry={load} />

  return (
    <div className="rounded-md border border-border bg-card divide-y divide-border">
      {CONSENT_TYPES.map((type) => {
        const status = statusFor(type)
        const granted = status === "GRANTED"
        return (
          <div key={type} className="flex items-center justify-between gap-4 px-4 py-3">
            <div>
              <p className="text-sm font-medium">{CONSENT_LABELS[type]}</p>
              <Badge variant={granted ? "default" : "outline"} className="mt-1">
                {granted ? "Concedido" : "Revogado"}
              </Badge>
            </div>
            <Button
              size="sm"
              variant={granted ? "outline" : "default"}
              disabled={busy === type}
              onClick={() => change(type, granted ? "revoke" : "grant")}
            >
              {granted ? "Revogar" : "Conceder"}
            </Button>
          </div>
        )
      })}
    </div>
  )
}

/* ------------------------------- Edit dialog ------------------------------- */
function EditCustomerDialog({ customer, onUpdated }: { customer: Customer; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState(customer.name)
  const [phone, setPhone] = useState(customer.phone)
  const [email, setEmail] = useState(customer.email ?? "")
  const [notes, setNotes] = useState(customer.notes ?? "")

  function onOpenChange(v: boolean) {
    if (v) {
      setName(customer.name); setPhone(customer.phone)
      setEmail(customer.email ?? ""); setNotes(customer.notes ?? "")
    }
    setOpen(v)
  }

  async function handleSave() {
    setSaving(true)
    try {
      await api.patch(`/customers/${customer.id}`, {
        name, phone, email: email || null, notes: notes || null,
      })
      toast.success("Cliente atualizado")
      setOpen(false)
      onUpdated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>Editar</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Editar cliente</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="ec-name">Nome *</Label>
            <Input id="ec-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-phone">Telefone *</Label>
            <Input id="ec-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-email">E-mail</Label>
            <Input id="ec-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-notes">Observações</Label>
            <Textarea id="ec-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
