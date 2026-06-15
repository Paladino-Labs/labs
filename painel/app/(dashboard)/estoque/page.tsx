"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { ArrowLeftRight, PackagePlus, Plus, Trash2 } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatBRLFromDecimal } from "@/lib/utils"
import type { StockProduct, Supplier, Product } from "@/types"
import { CLOSING_METHOD_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { MoneyInput } from "@/components/MoneyInput"
import { DateTimePicker } from "@/components/DateTimePicker"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface OrderItem { product_id: string; quantity: string; unit_cost: string }
interface Installment { amount: string; due_date: string }
interface ReceiveOrderResponse { payable_id: string; total_amount: string }

function isLowStock(p: StockProduct): boolean {
  if (p.stock == null || p.stock_min_alert == null) return false
  return p.stock <= parseFloat(p.stock_min_alert)
}

/* --------------------------- Receber pedido (J3) --------------------------- */
function ReceiveOrderDialog({ open, onOpenChange, onReceived, suppliers, products }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onReceived: (payableId: string) => void
  suppliers: Supplier[]
  products: Product[]
}) {
  const [supplierId, setSupplierId] = useState("none")
  const [items, setItems] = useState<OrderItem[]>([{ product_id: "", quantity: "", unit_cost: "" }])
  const [closingMethod, setClosingMethod] = useState("CASH_AT_CREATION")
  const [dueDate, setDueDate] = useState("")
  const [installments, setInstallments] = useState<Installment[]>([{ amount: "", due_date: "" }])
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setSupplierId("none")
      setItems([{ product_id: "", quantity: "", unit_cost: "" }])
      setClosingMethod("CASH_AT_CREATION")
      setDueDate(""); setInstallments([{ amount: "", due_date: "" }]); setNotes("")
    }
  }, [open])

  const previewTotal = items.reduce((s, it) => {
    const q = parseFloat(it.quantity), c = parseFloat(it.unit_cost)
    return s + (isNaN(q) || isNaN(c) ? 0 : q * c)
  }, 0)

  function updateItem(i: number, patch: Partial<OrderItem>) {
    setItems((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  }
  function updateInst(i: number, patch: Partial<Installment>) {
    setInstallments((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  }

  const itemsValid = items.length > 0 && items.every(
    (it) => it.product_id && parseFloat(it.quantity) > 0 && it.unit_cost !== "" && parseFloat(it.unit_cost) >= 0,
  )

  async function handleReceive(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        supplier_id: supplierId === "none" ? null : supplierId,
        items: items.map((it) => ({
          product_id: it.product_id,
          quantity: it.quantity,
          unit_cost: it.unit_cost,
        })),
        closing_method: closingMethod,
        notes: notes || null,
      }
      if (closingMethod === "INSTALLMENTS") {
        body.installments = installments.map((it) => ({
          amount: it.amount,
          due_date: it.due_date ? it.due_date.slice(0, 10) : null,
        }))
      } else if (dueDate) {
        body.due_date = dueDate.slice(0, 10)
      }
      const res = await api.post<ReceiveOrderResponse>("/stock/orders/", body)
      toast.success(
        `Pedido recebido — entrada registrada e conta a pagar criada (${formatBRLFromDecimal(res.total_amount)})`,
        {
          action: {
            label: "Ver conta a pagar",
            onClick: () => { window.location.href = `/payables?payable_id=${res.payable_id}` },
          },
        },
      )
      onOpenChange(false)
      onReceived(res.payable_id)
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao receber pedido")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Receber pedido</DialogTitle>
          <DialogDescription>Registra ENTRADA de estoque e cria conta a pagar automática.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleReceive} className="space-y-4 py-1 max-h-[65vh] overflow-y-auto pr-1">
          <div className="space-y-1">
            <Label>Fornecedor (opcional)</Label>
            <Select value={supplierId} onValueChange={(v) => v && setSupplierId(v)}>
              <SelectTrigger className="w-full">
                <SelectValue>{supplierId === "none" ? "Sem fornecedor" : (suppliers.find((s) => s.id === supplierId)?.name ?? "—")}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sem fornecedor</SelectItem>
                {suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Itens</Label>
            {items.map((it, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="flex-1 space-y-1">
                  {i === 0 && <span className="text-xs text-muted-foreground">Produto</span>}
                  <Select value={it.product_id || "none"} onValueChange={(v) => v && updateItem(i, { product_id: v === "none" ? "" : v })}>
                    <SelectTrigger className="w-full">
                      <SelectValue>{it.product_id ? (products.find((p) => p.id === it.product_id)?.name ?? "—") : "Selecione"}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {products.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="w-20 space-y-1">
                  {i === 0 && <span className="text-xs text-muted-foreground">Qtd</span>}
                  <Input type="number" min="0" step="any" value={it.quantity} onChange={(e) => updateItem(i, { quantity: e.target.value })} />
                </div>
                <div className="w-32 space-y-1">
                  {i === 0 && <span className="text-xs text-muted-foreground">Custo unit</span>}
                  <MoneyInput value={it.unit_cost} onChange={(v) => updateItem(i, { unit_cost: v })} />
                </div>
                <Button type="button" variant="ghost" size="icon-sm" disabled={items.length === 1}
                  onClick={() => setItems((prev) => prev.filter((_, idx) => idx !== i))}>
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              </div>
            ))}
            <Button type="button" variant="outline" size="sm"
              onClick={() => setItems((prev) => [...prev, { product_id: "", quantity: "", unit_cost: "" }])}>
              <Plus className="h-3.5 w-3.5" /> Adicionar item
            </Button>
          </div>

          <div className="space-y-1">
            <Label>Fechamento</Label>
            <Select value={closingMethod} onValueChange={(v) => v && setClosingMethod(v)}>
              <SelectTrigger className="w-full"><SelectValue>{CLOSING_METHOD_LABELS[closingMethod]}</SelectValue></SelectTrigger>
              <SelectContent>
                {Object.entries(CLOSING_METHOD_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>

          {closingMethod === "INSTALLMENTS" ? (
            <div className="space-y-2">
              <Label>Parcelas</Label>
              {installments.map((inst, i) => (
                <div key={i} className="flex items-end gap-2">
                  <div className="w-32"><MoneyInput value={inst.amount} onChange={(v) => updateInst(i, { amount: v })} /></div>
                  <div className="flex-1"><DateTimePicker value={inst.due_date} onChange={(v) => updateInst(i, { due_date: v })} /></div>
                  <Button type="button" variant="ghost" size="icon-sm" disabled={installments.length === 1}
                    onClick={() => setInstallments((prev) => prev.filter((_, idx) => idx !== i))}>
                    <Trash2 className="h-4 w-4 text-muted-foreground" />
                  </Button>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm"
                onClick={() => setInstallments((prev) => [...prev, { amount: "", due_date: "" }])}>
                <Plus className="h-3.5 w-3.5" /> Adicionar parcela
              </Button>
            </div>
          ) : (
            <div className="space-y-1">
              <Label htmlFor="ord-due">Vencimento</Label>
              <DateTimePicker id="ord-due" value={dueDate} onChange={setDueDate} />
            </div>
          )}

          <div className="space-y-1">
            <Label htmlFor="ord-notes">Notas (opcional)</Label>
            <Textarea id="ord-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-sm">
            <span className="text-muted-foreground">Total (prévia)</span>
            <span className="font-medium">{formatBRLFromDecimal(previewTotal)}</span>
          </div>

          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !itemsValid}>{saving ? "Recebendo…" : "Receber pedido"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function EstoquePage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"

  const [products, setProducts] = useState<StockProduct[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [catalogProducts, setCatalogProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showInactive, setShowInactive] = useState(false)
  const [orderOpen, setOrderOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setProducts(await api.get<StockProduct[]>(`/stock/?active_only=${showInactive ? "false" : "true"}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [showInactive])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (!canWrite) return
    api.get<Supplier[]>("/suppliers/").then(setSuppliers).catch(() => {})
    api.get<Product[]>("/products/").then(setCatalogProducts).catch(() => {})
  }, [canWrite])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Estoque" description="Saldo, custo médio e alertas mínimos.">
        <Button variant="outline" render={<Link href="/estoque/movimentacoes" />}>
          <ArrowLeftRight className="h-4 w-4" /> Movimentações
        </Button>
        {canWrite && (
          <Button onClick={() => setOrderOpen(true)}>
            <PackagePlus className="h-4 w-4" /> Receber pedido
          </Button>
        )}
      </PageHeader>

      <div className="flex items-center justify-end gap-2">
        <Label htmlFor="show-inactive" className="text-sm text-muted-foreground">Mostrar inativos</Label>
        <Switch id="show-inactive" checked={showInactive} onCheckedChange={setShowInactive} />
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : products.length === 0 ? (
        <EmptyState title="Nenhum produto em estoque" description="Receba um pedido para dar entrada de estoque." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Produto</th>
                <th className="px-4 py-3 text-left font-medium">Qtd</th>
                <th className="px-4 py-3 text-left font-medium">Alerta mín.</th>
                <th className="px-4 py-3 text-left font-medium">Custo médio</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {products.map((p) => (
                <tr key={p.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium">
                    <span className="flex items-center gap-2">
                      {p.name}
                      {isLowStock(p) && (
                        <Badge variant="outline" className="font-normal bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300">
                          Estoque baixo
                        </Badge>
                      )}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {p.stock != null
                      ? <span>{p.stock}{p.unit ? ` ${p.unit}` : ""}</span>
                      : <span className="text-xs text-muted-foreground opacity-50">Em breve</span>}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{p.stock_min_alert ?? "—"}</td>
                  <td className="px-4 py-3">{formatBRLFromDecimal(p.avg_cost)}</td>
                  <td className="px-4 py-3"><ActiveBadge active={p.active} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canWrite && (
        <ReceiveOrderDialog open={orderOpen} onOpenChange={setOrderOpen} onReceived={() => load()}
          suppliers={suppliers} products={catalogProducts} />
      )}
    </div>
  )
}
