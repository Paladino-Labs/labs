"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Pause, Play, X } from "lucide-react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { Subscription, SubscriptionPlan, Customer } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { SubscriptionBadge } from "@/components/FsmBadge"
import { CustomerAutocomplete } from "@/components/CustomerAutocomplete"
import { DateTimePicker } from "@/components/DateTimePicker"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const STATUS_LABELS: Record<string, string> = {
  all: "Todos os status",
  ACTIVE: "Ativa",
  PAUSED: "Pausada",
  OVERDUE: "Em atraso",
  SUSPENDED: "Suspensa",
  CANCELLED: "Cancelada",
}

function NewSubscriptionDialog({
  open, onOpenChange, plans, onCreated,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  plans: SubscriptionPlan[]
  onCreated: () => void
}) {
  const [customerId, setCustomerId] = useState("")
  const [planId, setPlanId] = useState("")
  const [firstBilling, setFirstBilling] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) { setCustomerId(""); setPlanId(""); setFirstBilling("") }
  }, [open])

  const planLabel = planId ? (plans.find((p) => p.plan_id === planId)?.name ?? "Selecionar…") : "Selecionar…"

  async function handleCreate() {
    if (!customerId || !planId) return
    setSaving(true)
    try {
      await api.post("/subscriptions", {
        customer_id: customerId,
        plan_id: planId,
        ...(firstBilling ? { first_billing_at: new Date(firstBilling).toISOString() } : {}),
      })
      toast.success("Assinatura criada")
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar assinatura")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Nova assinatura</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label>Cliente</Label>
            <CustomerAutocomplete
              value={customerId || null}
              onChange={(id) => setCustomerId(id)}
              placeholder="Selecionar cliente…"
            />
          </div>
          <div className="space-y-1">
            <Label>Plano</Label>
            <Select value={planId} onValueChange={(v) => v && setPlanId(v)}>
              <SelectTrigger className="w-full"><SelectValue>{planLabel}</SelectValue></SelectTrigger>
              <SelectContent>
                {plans.filter((p) => p.is_active).map((p) => (
                  <SelectItem key={p.plan_id} value={p.plan_id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="sub-first">Primeira cobrança (opcional)</Label>
            <DateTimePicker id="sub-first" value={firstBilling} onChange={setFirstBilling} />
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleCreate} disabled={saving || !customerId || !planId}>
            {saving ? "Criando…" : "Criar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function SubscriptionsPage() {
  const [subs, setSubs] = useState<Subscription[]>([])
  const [planMap, setPlanMap] = useState<Map<string, string>>(new Map())
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [customerMap, setCustomerMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [query, setQuery] = useState("")
  const [statusFilter, setStatusFilter] = useState("all")
  const [newOpen, setNewOpen] = useState(false)
  const [cancelTarget, setCancelTarget] = useState<Subscription | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.get<Subscription[]>("/subscriptions")
      setSubs(data)
      try {
        const [pl, custs] = await Promise.all([
          api.get<SubscriptionPlan[]>("/subscription-plans"),
          api.get<Customer[]>("/customers/"),
        ])
        setPlans(pl)
        setPlanMap(new Map(pl.map((p) => [p.plan_id, p.name])))
        setCustomerMap(new Map(custs.map((c) => [c.id, c.name])))
      } catch { /* nomes ficam como id */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const filtered = useMemo(() => subs.filter((s) => {
    if (statusFilter !== "all" && s.status !== statusFilter) return false
    if (query.trim()) {
      const name = (customerMap.get(s.customer_id) ?? s.customer_id).toLowerCase()
      if (!name.includes(query.trim().toLowerCase())) return false
    }
    return true
  }), [subs, statusFilter, query, customerMap])

  async function transition(sub: Subscription, action: "pause" | "resume") {
    setBusy(sub.subscription_id)
    try {
      await api.patch(`/subscriptions/${sub.subscription_id}/${action}`, {})
      toast.success(action === "pause" ? "Assinatura pausada" : "Assinatura retomada")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro na operação")
    } finally {
      setBusy(null)
    }
  }

  async function handleCancel() {
    if (!cancelTarget) return
    setBusy(cancelTarget.subscription_id)
    try {
      await api.patch(`/subscriptions/${cancelTarget.subscription_id}/cancel`, {})
      toast.success("Assinatura cancelada")
      setCancelTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao cancelar")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Assinaturas" title="Instâncias" description="Assinaturas ativas, pausadas e em cobrança.">
        <Button onClick={() => setNewOpen(true)}>+ Nova assinatura</Button>
      </PageHeader>

      <div className="flex flex-wrap gap-4 rounded-lg border border-border bg-card p-4">
        <Input placeholder="Buscar cliente…" value={query} onChange={(e) => setQuery(e.target.value)} className="max-w-xs flex-1" />
        <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
          <SelectTrigger className="w-56"><SelectValue>{STATUS_LABELS[statusFilter]}</SelectValue></SelectTrigger>
          <SelectContent>
            {Object.keys(STATUS_LABELS).map((s) => (
              <SelectItem key={s} value={s}>{STATUS_LABELS[s]}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : filtered.length === 0 ? (
        <EmptyState title="Nenhuma assinatura" description="Nenhuma assinatura para os filtros selecionados." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Plano</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Próx. cobrança</th>
                <th className="px-4 py-3 text-left font-medium">Em atraso desde</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filtered.map((s) => {
                const disabled = busy === s.subscription_id
                return (
                  <tr key={s.subscription_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{customerMap.get(s.customer_id) ?? s.customer_id}</td>
                    <td className="px-4 py-3">{planMap.get(s.plan_id) ?? s.plan_id}</td>
                    <td className="px-4 py-3"><SubscriptionBadge status={s.status} /></td>
                    <td className="px-4 py-3 text-muted-foreground">{s.next_billing_at ? formatDateTime(s.next_billing_at) : "—"}</td>
                    <td className="px-4 py-3 text-muted-foreground">{s.overdue_since ? formatDateTime(s.overdue_since) : "—"}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-2">
                        {s.status === "ACTIVE" && (
                          <Button size="sm" variant="outline" disabled={disabled} onClick={() => transition(s, "pause")}>
                            <Pause className="h-3.5 w-3.5" /> Pausar
                          </Button>
                        )}
                        {s.status === "PAUSED" && (
                          <Button size="sm" variant="outline" disabled={disabled} onClick={() => transition(s, "resume")}>
                            <Play className="h-3.5 w-3.5" /> Retomar
                          </Button>
                        )}
                        {(s.status === "ACTIVE" || s.status === "PAUSED" || s.status === "OVERDUE") && (
                          <Button size="sm" variant="ghost" className="text-destructive" disabled={disabled} onClick={() => setCancelTarget(s)}>
                            <X className="h-3.5 w-3.5" /> Cancelar
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <NewSubscriptionDialog open={newOpen} onOpenChange={setNewOpen} plans={plans} onCreated={load} />

      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar assinatura</DialogTitle>
            <DialogDescription>
              Cancelar a assinatura de {cancelTarget ? (customerMap.get(cancelTarget.customer_id) ?? cancelTarget.customer_id) : ""}?
              Esta ação não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleCancel}>Cancelar assinatura</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
