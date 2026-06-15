"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Pencil, Power } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRLFromDecimal } from "@/lib/utils"
import type { SubscriptionPlan, Service } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const GENERIC = "__generic__"

function PlanFormDialog({
  open, onOpenChange, initial, services, onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: SubscriptionPlan | null
  services: Service[]
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [cotas, setCotas] = useState("")
  const [price, setPrice] = useState("")
  const [cycle, setCycle] = useState("30")
  const [rollover, setRollover] = useState(false)
  const [serviceId, setServiceId] = useState(GENERIC)
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? "")
      setCotas(initial ? String(initial.cotas_per_cycle) : "")
      setPrice(initial?.price ?? "")
      setCycle(initial ? String(initial.cycle_days) : "30")
      setRollover(initial?.rollover_enabled ?? false)
      setServiceId(initial?.service_id ?? GENERIC)
      setIsActive(initial?.is_active ?? true)
    }
  }, [open, initial])

  const serviceLabel = serviceId === GENERIC
    ? "Genérico"
    : (services.find((s) => s.id === serviceId)?.name ?? "Selecionar serviço")

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const body = {
        name: name.trim(),
        cotas_per_cycle: parseInt(cotas, 10),
        price: parseFloat(price),
        cycle_days: parseInt(cycle, 10) || 30,
        rollover_enabled: rollover,
        service_id: serviceId === GENERIC ? null : serviceId,
        ...(initial ? { is_active: isActive } : {}),
      }
      if (initial) {
        await api.patch(`/subscription-plans/${initial.plan_id}`, body)
        toast.success("Plano atualizado")
      } else {
        await api.post("/subscription-plans", body)
        toast.success("Plano criado")
      }
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar plano")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Editar plano" : "Novo plano"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="sp-name">Nome *</Label>
            <Input id="sp-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="sp-cotas">Cotas / ciclo *</Label>
              <Input id="sp-cotas" type="number" min="1" value={cotas}
                onChange={(e) => setCotas(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sp-price">Preço (R$) *</Label>
              <Input id="sp-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required placeholder="0.00" />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="sp-cycle">Ciclo (dias)</Label>
              <Input id="sp-cycle" type="number" min="1" value={cycle}
                onChange={(e) => setCycle(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label>Serviço</Label>
              <Select value={serviceId} onValueChange={(v) => v && setServiceId(v)}>
                <SelectTrigger className="w-full"><SelectValue>{serviceLabel}</SelectValue></SelectTrigger>
                <SelectContent>
                  <SelectItem value={GENERIC}>Genérico (qualquer serviço)</SelectItem>
                  {services.filter((s) => s.active).map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <Label htmlFor="sp-rollover">Rollover (cotas não usadas passam ao próximo ciclo)</Label>
            <Switch id="sp-rollover" checked={rollover} onCheckedChange={setRollover} />
          </div>
          {initial && (
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <Label htmlFor="sp-active">Ativo</Label>
              <Switch id="sp-active" checked={isActive} onCheckedChange={setIsActive} />
            </div>
          )}
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !name.trim()}>
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function SubscriptionPlansPage() {
  const [plans, setPlans] = useState<SubscriptionPlan[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SubscriptionPlan | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [pl, svc] = await Promise.all([
        api.get<SubscriptionPlan[]>("/subscription-plans"),
        api.get<Service[]>("/services/").catch(() => [] as Service[]),
      ])
      setPlans(pl)
      setServices(svc)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const serviceMap = useMemo(() => new Map(services.map((s) => [s.id, s])), [services])

  async function toggleActive(plan: SubscriptionPlan) {
    try {
      await api.patch(`/subscription-plans/${plan.plan_id}`, { is_active: !plan.is_active })
      toast.success(plan.is_active ? "Plano desativado" : "Plano ativado")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao alterar status")
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Assinaturas" title="Planos" description="Configure planos recorrentes.">
        <Button onClick={() => { setEditing(null); setFormOpen(true) }}>+ Novo plano</Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : plans.length === 0 ? (
        <EmptyState title="Nenhum plano" description="Crie o primeiro plano de assinatura." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Serviço</TableHead>
                <TableHead className="text-right">Cotas/ciclo</TableHead>
                <TableHead className="text-right">Preço</TableHead>
                <TableHead>Ciclo</TableHead>
                <TableHead>Rollover</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {plans.map((plan) => (
                <TableRow key={plan.plan_id}>
                  <TableCell className="font-medium">{plan.name}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {plan.service_id ? (serviceMap.get(plan.service_id)?.name ?? plan.service_id) : "Genérico"}
                  </TableCell>
                  <TableCell className="text-right">{plan.cotas_per_cycle}</TableCell>
                  <TableCell className="text-right">{formatBRLFromDecimal(plan.price)}</TableCell>
                  <TableCell>{plan.cycle_days} dias</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="font-normal">{plan.rollover_enabled ? "Sim" : "Não"}</Badge>
                  </TableCell>
                  <TableCell><StatusBadge active={plan.is_active} /></TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="ghost" size="icon-sm" onClick={() => { setEditing(plan); setFormOpen(true) }}>
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => toggleActive(plan)}
                        title={plan.is_active ? "Desativar" : "Ativar"}
                      >
                        <Power className="h-3.5 w-3.5" />
                        {plan.is_active ? "Desativar" : "Ativar"}
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <PlanFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        services={services}
        onSaved={load}
      />
    </div>
  )
}
