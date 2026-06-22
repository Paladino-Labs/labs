"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Pencil, Trash2, ShoppingCart, Plus, X } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { formatBRLFromDecimal, cn } from "@/lib/utils"
import type { Package, Service, Product } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CustomerAutocomplete } from "@/components/CustomerAutocomplete"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { PAYMENT_METHOD_GROUPS, PAYMENT_METHOD_OPTIONS } from "@/lib/constants"

interface ItemDraft {
  item_type:  "SERVICE" | "PRODUCT"
  service_id: string | null
  product_id: string | null
  quantity:   number
}

/* ----------------------------- Form (criar/editar) ----------------------------- */
function PackageFormDialog({
  open, onOpenChange, initial, services, products, onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: Package | null
  services: Service[]
  products: Product[]
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [items, setItems] = useState<ItemDraft[]>([
    { item_type: "SERVICE", service_id: null, product_id: null, quantity: 1 },
  ])
  const [price, setPrice] = useState("")
  const [validity, setValidity] = useState("")
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? "")
      setItems([{ item_type: "SERVICE", service_id: null, product_id: null, quantity: 1 }])
      setPrice(initial?.price ?? "")
      setValidity(initial?.validity_days != null ? String(initial.validity_days) : "")
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
        price:         parseFloat(price),
        validity_days: validity ? parseInt(validity, 10) : null,
        ...(initial ? { is_active: isActive } : {}),
      }
      if (initial) {
        await api.patch(`/packages/${initial.package_id}`, body)
        toast.success("Pacote atualizado")
      } else {
        await api.post("/packages", body)
        toast.success("Pacote criado")
      }
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar pacote")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] grid-rows-[auto_minmax(0,1fr)]">
        <DialogHeader>
          <DialogTitle>{initial ? "Editar pacote" : "Novo pacote"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSave} className="flex min-h-0 flex-col gap-4">
          <div className="space-y-4 overflow-y-auto py-1">
          <div className="space-y-1">
            <Label htmlFor="pk-name">Nome *</Label>
            <Input id="pk-name" value={name} onChange={(e) => setName(e.target.value)} required />
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
                Para alterar os itens, crie um novo pacote.
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Itens do pacote *</Label>
              {items.map((item, i) => {
                const serviceLabel = services.find((s) => s.id === item.service_id)?.name
                const productLabel = products.find((p) => p.id === item.product_id)?.name
                return (
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
                    <div className="min-w-0 flex-1">
                      {item.item_type === "SERVICE" ? (
                        <Select
                          value={item.service_id ?? ""}
                          onValueChange={(v) => patchItem(i, { service_id: v || null })}
                        >
                          <SelectTrigger className="w-full">
                            <SelectValue placeholder="Selecionar serviço…">{serviceLabel}</SelectValue>
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
                            <SelectValue placeholder="Selecionar produto…">{productLabel}</SelectValue>
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
                      className="w-20 shrink-0"
                      placeholder="Qtd"
                    />

                    {items.length > 1 && (
                      <button type="button" onClick={() => removeItem(i)}
                        className="text-muted-foreground hover:text-destructive transition-colors px-1 shrink-0">
                        <X size={16} strokeWidth={1.5} />
                      </button>
                    )}
                  </div>
                </div>
                )
              })}

              <button type="button" onClick={addItem}
                className="flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-border py-2 text-sm text-muted-foreground hover:bg-muted/30 transition-colors">
                <Plus size={14} strokeWidth={1.5} /> Adicionar item
              </button>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pk-price">Preço (R$) *</Label>
              <Input id="pk-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required placeholder="0.00" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="pk-validity">Validade (dias)</Label>
              <Input id="pk-validity" type="number" min="1" value={validity}
                onChange={(e) => setValidity(e.target.value)} placeholder="Sem validade" />
            </div>
          </div>
          {initial && (
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <Label htmlFor="pk-active">Ativo</Label>
              <Switch id="pk-active" checked={isActive} onCheckedChange={setIsActive} />
            </div>
          )}
          </div>
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

/* ------------------------------- Venda (stepper) ------------------------------- */
const STEPS = ["1. Cliente", "2. Plano", "3. Pagamento", "4. Confirmar"]

function SellPackageDialog({
  pkg, userId, onClose, onSold,
}: {
  pkg: Package | null
  userId: string | null
  onClose: () => void
  onSold: () => void
}) {
  const [step, setStep] = useState(0)
  const [customerId, setCustomerId] = useState("")
  const [customerName, setCustomerName] = useState("")
  const [method, setMethod] = useState("")
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (pkg) { setStep(0); setCustomerId(""); setCustomerName(""); setMethod("") }
  }, [pkg])

  if (!pkg) return null

  const methodLabel = PAYMENT_METHOD_OPTIONS.find((o) => o.key === method)?.label ?? ""

  const canNext =
    (step === 0 && !!customerId) ||
    (step === 1) ||
    (step === 2 && !!method) ||
    step === 3

  async function handleConfirm() {
    if (!pkg) return
    setSubmitting(true)
    try {
      const res = await api.post<{ purchase_id: string; payment_id?: string | null }>(
        `/packages/${pkg.package_id}/sell`,
        { customer_id: customerId, payment_method: method, ...(userId ? { seller_user_id: userId } : {}) },
      )
      toast.success("Pacote vendido — pagamento pendente de confirmação", {
        description: res.payment_id ? "Confirme em Pagamentos." : undefined,
        action: res.payment_id
          ? { label: "Ver pagamento", onClick: () => { window.location.href = `/payments/${res.payment_id}` } }
          : undefined,
      })
      onClose()
      onSold()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao vender pacote")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={!!pkg} onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Vender pacote</DialogTitle>
          <DialogDescription>{pkg.name}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] uppercase tracking-wide">
          {STEPS.map((s, i) => (
            <span key={s} className={cn(i === step ? "text-foreground font-medium" : "text-muted-foreground/60")}>
              {s}
            </span>
          ))}
        </div>

        <div className="py-1">
          {step === 0 && (
            <div className="space-y-1">
              <Label>Cliente</Label>
              <CustomerAutocomplete
                value={customerId || null}
                onChange={(id, name) => { setCustomerId(id); setCustomerName(name) }}
                placeholder="Selecionar cliente…"
              />
            </div>
          )}

          {step === 1 && (
            <div className="rounded-lg border border-border bg-card p-4 text-sm space-y-2">
              <Row label="Plano" value={pkg.name} />
              {pkg.items.map((it, i) => (
                <Row key={i}
                  label={it.service_name ?? it.product_name ?? "Item"}
                  value={`${it.quantity}× cota${it.quantity > 1 ? "s" : ""}`}
                />
              ))}
              <Row label="Total de cotas" value={String(pkg.total_cotas)} />
              <Row label="Preço" value={formatBRLFromDecimal(pkg.price)} />
              <Row label="Validade" value={pkg.validity_days != null ? `${pkg.validity_days} dias` : "Sem validade"} />
            </div>
          )}

          {step === 2 && (
            <div className="space-y-4">
              {PAYMENT_METHOD_GROUPS.map((group) => (
                <div key={group} className="space-y-2">
                  <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">{group}</p>
                  <div className="space-y-2">
                    {PAYMENT_METHOD_OPTIONS.filter((o) => o.group === group).map((o) => (
                      <button
                        key={o.key}
                        type="button"
                        onClick={() => setMethod(o.key)}
                        className={cn(
                          "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors",
                          method === o.key ? "border-primary bg-primary/5" : "border-border hover:bg-muted/50",
                        )}
                      >
                        <span className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full border",
                          method === o.key ? "border-primary" : "border-muted-foreground/40",
                        )}>
                          {method === o.key && <span className="h-2 w-2 rounded-full bg-primary" />}
                        </span>
                        {o.label}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          {step === 3 && (
            <div className="space-y-3">
              <div className="rounded-lg border border-border bg-card p-4 text-sm space-y-2">
                <Row label="Cliente" value={customerName || customerId} />
                <Row label="Plano" value={pkg.name} />
                <Row label="Pagamento" value={methodLabel} />
                <div className="border-t border-border pt-2">
                  <Row label="Total" value={formatBRLFromDecimal(pkg.price)} strong />
                </div>
              </div>
              <p className="text-xs text-muted-foreground">
                A venda cria a compra como pagamento pendente; confirme no módulo de pagamentos.
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          {step > 0 ? (
            <Button variant="ghost" onClick={() => setStep((s) => s - 1)}>Voltar</Button>
          ) : (
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          )}
          {step < 3 ? (
            <Button onClick={() => setStep((s) => s + 1)} disabled={!canNext}>Próximo</Button>
          ) : (
            <Button onClick={handleConfirm} disabled={submitting}>
              {submitting ? "Vendendo…" : "Confirmar venda"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className={cn("text-right", strong && "font-medium text-base")}>{value}</span>
    </div>
  )
}

/* ----------------------------------- Página ----------------------------------- */
export default function PacotesPage() {
  const { userId } = useAuth()

  const [packages, setPackages] = useState<Package[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Package | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Package | null>(null)
  const [selling, setSelling] = useState<Package | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [pkgs, svc, prod] = await Promise.all([
        api.get<Package[]>("/packages"),
        api.get<Service[]>("/services/").catch(() => [] as Service[]),
        api.get<Product[]>("/products/").catch(() => [] as Product[]),
      ])
      setPackages(pkgs)
      setServices(svc)
      setProducts(prod)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await api.delete(`/packages/${deleteTarget.package_id}`)
      toast.success("Pacote excluído")
      setDeleteTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao excluir pacote")
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Comercial" title="Tipos de pacotes" description="Tipos de pacote para venda avulsa.">
        <Button variant="outline" render={<Link href="/pacotes/compras" />}>Vendas</Button>
        <Button onClick={() => { setEditing(null); setFormOpen(true) }}>+ Novo tipo de pacote</Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : packages.length === 0 ? (
        <EmptyState title="Nenhum pacote" description="Crie o primeiro plano de pacote para vender." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Itens</TableHead>
                <TableHead className="text-right">Cotas</TableHead>
                <TableHead className="text-right">Preço</TableHead>
                <TableHead>Validade</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {packages.map((pkg) => (
                <TableRow key={pkg.package_id}>
                  <TableCell className="font-medium">{pkg.name}</TableCell>
                  <TableCell className="text-sm">
                    {pkg.items.length === 0
                      ? <span className="text-muted-foreground">—</span>
                      : pkg.items.length === 1
                        ? `${pkg.items[0].service_name ?? pkg.items[0].product_name ?? "Item"} ×${pkg.items[0].quantity}`
                        : `${pkg.items.length} itens · ${pkg.total_cotas} cotas`}
                  </TableCell>
                  <TableCell className="text-right">{pkg.total_cotas}</TableCell>
                  <TableCell className="text-right">{formatBRLFromDecimal(pkg.price)}</TableCell>
                  <TableCell>{pkg.validity_days != null ? `${pkg.validity_days} dias` : "Sem validade"}</TableCell>
                  <TableCell><StatusBadge active={pkg.is_active} /></TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button size="sm" variant="outline" disabled={!pkg.is_active} onClick={() => setSelling(pkg)}>
                        <ShoppingCart className="h-3.5 w-3.5" /> Vender
                      </Button>
                      <Button variant="ghost" size="icon-sm" onClick={() => { setEditing(pkg); setFormOpen(true) }}>
                        <Pencil />
                      </Button>
                      <Button variant="ghost" size="icon-sm" className="text-destructive" onClick={() => setDeleteTarget(pkg)}>
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <PackageFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        services={services}
        products={products}
        onSaved={load}
      />

      <SellPackageDialog
        pkg={selling}
        userId={userId}
        onClose={() => setSelling(null)}
        onSold={load}
      />

      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir pacote</DialogTitle>
            <DialogDescription>
              Excluir o pacote “{deleteTarget?.name}”? Esta ação não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDelete}>Excluir</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
