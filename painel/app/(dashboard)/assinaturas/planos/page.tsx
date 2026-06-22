"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Pencil, Power, Plus, X } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRLFromDecimal, cn } from "@/lib/utils"
import type { SubscriptionPlan, Service, Product } from "@/types"
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

interface ItemDraft {
  item_type:  "SERVICE" | "PRODUCT"
  service_id: string | null
  product_id: string | null
  quantity:   number
}

function PlanFormDialog({
  open, onOpenChange, initial, services, products, onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: SubscriptionPlan | null
  services: Service[]
  products: Product[]
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [items, setItems] = useState<ItemDraft[]>([
    { item_type: "SERVICE", service_id: null, product_id: null, quantity: 1 },
  ])
  const [price, setPrice] = useState("")
  const [cycle, setCycle] = useState("30")
  const [rollover, setRollover] = useState(false)
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? "")
      setItems([{ item_type: "SERVICE", service_id: null, product_id: null, quantity: 1 }])
      setPrice(initial?.price ?? "")
      setCycle(initial ? String(initial.cycle_days) : "30")
      setRollover(initial?.rollover_enabled ?? false)
      setIsActive(initial?.is_active ?? true)
    }
  }, [open, initial])

  function addItem() {
    setItems((prev) => [...prev, { item_type: "SERVICE", service_id: null, product_id: null, quantity: 1 }])
  }
  function removeItem(index: number) {
    setItems((prev) => prev.filter((_, i) => i !== index))
  }
  function patchItem(index: number, patch: Partial<ItemDraft>) {
    setItems((prev) => prev.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()

    const invalid = items.some((it) =>
      (it.item_type === "SERVICE" && !it.service_id) ||
      (it.item_type === "PRODUCT" && !it.product_id)
    )
    if (invalid) { toast.error("Selecione o serviço ou produto de cada item."); return }

    setSaving(true)
    try {
      const body = {
        name: name.trim(),
        items: items.map((it) => ({
          item_type:  it.item_type,
          service_id: it.item_type === "SERVICE" ? it.service_id : null,
          product_id: it.item_type === "PRODUCT" ? it.product_id : null,
          quantity:   it.quantity,
        })),
        price:            parseFloat(price),
        cycle_days:       parseInt(cycle, 10) || 30,
        rollover_enabled: rollover,
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

          {initial ? (
            <div className="space-y-1">
              <Label>Itens</Label>
              <div className="flex flex-wrap gap-2">
                {initial.items.map((it) => (
                  <span key={it.item_id}
                    className="rounded-full border border-border bg-muted px-3 py-1 text-xs text-muted-foreground">
                    {it.service_name ?? it.product_name ?? it.item_type} × {it.quantity}
                  </span>
                ))}
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Para alterar os itens, crie um novo plano.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Itens do plano *</Label>
              {items.map((item, i) => (
                <div key={i} className="flex flex-col gap-2 rounded-lg border border-border p-3">
                  <div className="flex gap-2">
                    {(["SERVICE", "PRODUCT"] as const).map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => patchItem(i, { item_type: type, service_id: null, product_id: null })}
                        className={cn(
                          "flex-1 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                          item.item_type === type
                            ? "border-primary bg-primary/5 text-primary"
                            : "border-border text-muted-foreground hover:bg-muted/50",
                        )}
                      >
                        {type === "SERVICE" ? "Serviço" : "Produto"}
                      </button>
                    ))}
                  </div>

                  <div className="flex gap-2">
                    <div className="flex-1">
                      {item.item_type === "SERVICE" ? (
                        <Select
                          value={item.service_id ?? ""}
                          onValueChange={(v) => patchItem(i, { service_id: v || null })}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Selecionar serviço…" />
                          </SelectTrigger>
                          <SelectContent>
                            {services.filter((s) => s.active).map((s) => (
                              <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      ) : (
                        <Select
                          value={item.product_id ?? ""}
                          onValueChange={(v) => patchItem(i, { product_id: v || null })}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Selecionar produto…" />
                          </SelectTrigger>
                          <SelectContent>
                            {products.filter((p) => p.active).map((p) => (
                              <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}
                    </div>

                    <Input
                      type="number" min="1" value={String(item.quantity)}
                      onChange={(e) => patchItem(i, { quantity: parseInt(e.target.value) || 1 })}
                      className="w-20"
                      placeholder="Qtd"
                    />

                    {items.length > 1 && (
                      <button type="button" onClick={() => removeItem(i)}
                        className="text-muted-foreground hover:text-destructive transition-colors px-1">
                        <X size={16} strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                </div>
              ))}

              <button type="button" onClick={addItem}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-2 text-sm text-muted-foreground hover:bg-muted/30 transition-colors">
                <Plus size={14} strokeWidth={1.5} /> Adicionar item
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="sp-price">Preço (R$) *</Label>
              <Input id="sp-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required placeholder="0.00" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="sp-cycle">Ciclo (dias)</Label>
              <Input id="sp-cycle" type="number" min="1" value={cycle}
                onChange={(e) => setCycle(e.target.value)} />
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
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<SubscriptionPlan | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [pl, svc, prod] = await Promise.all([
        api.get<SubscriptionPlan[]>("/subscription-plans"),
        api.get<Service[]>("/services/").catch(() => [] as Service[]),
        api.get<Product[]>("/products/").catch(() => [] as Product[]),
      ])
      setPlans(pl)
      setServices(svc)
      setProducts(prod)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

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
                <TableHead>Itens</TableHead>
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
                  <TableCell className="text-sm">
                    {plan.items.length === 0
                      ? <span className="text-muted-foreground">—</span>
                      : plan.items.length === 1
                        ? `${plan.items[0].service_name ?? plan.items[0].product_name ?? "Item"} ×${plan.items[0].quantity}`
                        : `${plan.items.length} itens · ${plan.total_cotas_per_cycle} cotas`}
                  </TableCell>
                  <TableCell className="text-right">{plan.total_cotas_per_cycle}</TableCell>
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
        products={products}
        onSaved={load}
      />
    </div>
  )
}
