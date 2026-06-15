"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Pencil, Trash2, ShoppingCart } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { formatBRLFromDecimal, cn } from "@/lib/utils"
import type { Package, Service } from "@/types"
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

const GENERIC = "__generic__"

function serviceName(pkg: Package, map: Map<string, Service>): string {
  if (!pkg.service_id) return "Genérico"
  return map.get(pkg.service_id)?.name ?? pkg.service_id
}

/* ----------------------------- Form (criar/editar) ----------------------------- */
function PackageFormDialog({
  open, onOpenChange, initial, services, onSaved,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: Package | null
  services: Service[]
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [cotas, setCotas] = useState("")
  const [price, setPrice] = useState("")
  const [serviceId, setServiceId] = useState(GENERIC)
  const [validity, setValidity] = useState("")
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(initial?.name ?? "")
      setCotas(initial ? String(initial.total_cotas) : "")
      setPrice(initial?.price ?? "")
      setServiceId(initial?.service_id ?? GENERIC)
      setValidity(initial?.validity_days != null ? String(initial.validity_days) : "")
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
        total_cotas: parseInt(cotas, 10),
        price: parseFloat(price),
        service_id: serviceId === GENERIC ? null : serviceId,
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
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Editar pacote" : "Novo pacote"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="pk-name">Nome *</Label>
            <Input id="pk-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pk-cotas">Cotas *</Label>
              <Input id="pk-cotas" type="number" min="1" value={cotas}
                onChange={(e) => setCotas(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="pk-price">Preço (R$) *</Label>
              <Input id="pk-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required placeholder="0.00" />
            </div>
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
          <div className="space-y-1">
            <Label htmlFor="pk-validity">Validade (dias)</Label>
            <Input id="pk-validity" type="number" min="1" value={validity}
              onChange={(e) => setValidity(e.target.value)} placeholder="Sem validade" />
          </div>
          {initial && (
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <Label htmlFor="pk-active">Ativo</Label>
              <Switch id="pk-active" checked={isActive} onCheckedChange={setIsActive} />
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
              <Row label="Cotas" value={String(pkg.total_cotas)} />
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Package | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Package | null>(null)
  const [selling, setSelling] = useState<Package | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [pkgs, svc] = await Promise.all([
        api.get<Package[]>("/packages"),
        api.get<Service[]>("/services/").catch(() => [] as Service[]),
      ])
      setPackages(pkgs)
      setServices(svc)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const serviceMap = useMemo(() => new Map(services.map((s) => [s.id, s])), [services])

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
      <PageHeader eyebrow="Comercial" title="Pacotes" description="Planos de pacote para venda avulsa.">
        <Button variant="outline" render={<Link href="/pacotes/compras" />}>Histórico</Button>
        <Button onClick={() => { setEditing(null); setFormOpen(true) }}>+ Novo plano</Button>
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
                <TableHead>Serviço</TableHead>
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
                  <TableCell className="text-muted-foreground">{serviceName(pkg, serviceMap)}</TableCell>
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
