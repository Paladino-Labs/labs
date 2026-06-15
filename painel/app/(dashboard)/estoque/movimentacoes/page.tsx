"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { ArrowDown, ArrowUp } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { StockMovement, StockProduct } from "@/types"
import { STOCK_MOVEMENT_TYPE_LABELS, STOCK_MOVEMENT_TYPE_OPTIONS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const TYPE_CLASS: Record<string, string> = {
  ENTRADA:     "bg-emerald-500/15 text-emerald-700 border-emerald-500/30 dark:text-emerald-300",
  VENDA:       "bg-sky-500/15 text-sky-700 border-sky-500/30 dark:text-sky-300",
  USO_INTERNO: "bg-muted text-muted-foreground border-border",
  PERDA:       "bg-destructive/15 text-destructive border-destructive/30",
  AJUSTE:      "bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-300",
}

function QuantityCell({ type, quantity }: { type: string; quantity: string }) {
  const n = parseFloat(quantity)
  const positive = type === "ENTRADA" || (type === "AJUSTE" && n >= 0)
  return (
    <span className={cn("inline-flex items-center gap-1", positive ? "text-success" : "text-destructive")}>
      {positive ? <ArrowUp className="h-3.5 w-3.5" /> : <ArrowDown className="h-3.5 w-3.5" />}
      {quantity}
    </span>
  )
}

/* ------------------------------ Registrar ------------------------------ */
function RegisterMovementDialog({ open, onOpenChange, onSaved, products }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSaved: () => void
  products: StockProduct[]
}) {
  const [productId, setProductId] = useState("")
  const [type, setType] = useState("VENDA")
  const [quantity, setQuantity] = useState("")
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) { setProductId(""); setType("VENDA"); setQuantity(""); setNotes("") }
  }, [open])

  const notesRequired = type === "AJUSTE"

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/stock/movements/", {
        product_id: productId,
        movement_type: type,
        quantity,
        notes: notes || null,
      })
      toast.success("Movimento registrado")
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao registrar movimento")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Registrar movimento</DialogTitle>
          <DialogDescription>ENTRADA só via &ldquo;Receber pedido&rdquo;.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label>Produto</Label>
            <Select value={productId || "none"} onValueChange={(v) => v && setProductId(v === "none" ? "" : v)}>
              <SelectTrigger className="w-full">
                <SelectValue>{productId ? (products.find((p) => p.id === productId)?.name ?? "—") : "Selecione"}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {products.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Tipo</Label>
            <Select value={type} onValueChange={(v) => v && setType(v)}>
              <SelectTrigger className="w-full"><SelectValue>{STOCK_MOVEMENT_TYPE_LABELS[type]}</SelectValue></SelectTrigger>
              <SelectContent>
                {STOCK_MOVEMENT_TYPE_OPTIONS.map((t) => <SelectItem key={t} value={t}>{STOCK_MOVEMENT_TYPE_LABELS[t]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="mv-qty">Quantidade</Label>
            <Input id="mv-qty" type="number" step="any" value={quantity} onChange={(e) => setQuantity(e.target.value)}
              placeholder="Use sinal negativo para AJUSTE de saída" required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mv-notes">Notas {notesRequired && "*"}</Label>
            <Textarea id="mv-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} required={notesRequired} />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !productId || !quantity || (notesRequired && !notes.trim())}>
              {saving ? "Registrando…" : "Registrar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function MovimentacoesEstoquePage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"

  const [movements, setMovements] = useState<StockMovement[]>([])
  const [products, setProducts] = useState<StockProduct[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [registerOpen, setRegisterOpen] = useState(false)

  const [productFilter, setProductFilter] = useState("all")
  const [typeFilter, setTypeFilter] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const productMap = useMemo(() => new Map(products.map((p) => [p.id, p.name])), [products])

  useEffect(() => {
    api.get<StockProduct[]>("/stock/?active_only=false").then(setProducts).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (productFilter !== "all") params.set("product_id", productFilter)
    if (typeFilter !== "all") params.set("movement_type", typeFilter)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    const q = params.toString()
    try {
      setMovements(await api.get<StockMovement[]>(`/stock/movements/${q ? `?${q}` : ""}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [productFilter, typeFilter, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Estoque" title="Movimentações" description="Histórico de entradas, vendas, usos internos, perdas e ajustes.">
        {canWrite && <Button onClick={() => setRegisterOpen(true)}>+ Registrar movimento</Button>}
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="space-y-1">
          <Label>Produto</Label>
          <Select value={productFilter} onValueChange={(v) => v && setProductFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{productFilter === "all" ? "Todos" : (productMap.get(productFilter) ?? "—")}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {products.map((p) => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Tipo</Label>
          <Select value={typeFilter} onValueChange={(v) => v && setTypeFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{typeFilter === "all" ? "Todos" : STOCK_MOVEMENT_TYPE_LABELS[typeFilter]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {Object.entries(STOCK_MOVEMENT_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="mv-from">De</Label>
          <Input id="mv-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="mv-to">Até</Label>
          <Input id="mv-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : movements.length === 0 ? (
        <EmptyState title="Nenhuma movimentação" description="Nenhum movimento para os filtros selecionados." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Produto</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-left font-medium">Quantidade</th>
                <th className="px-4 py-3 text-left font-medium">Custo unit.</th>
                <th className="px-4 py-3 text-left font-medium">Origem</th>
                <th className="px-4 py-3 text-left font-medium">Notas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {movements.map((m) => (
                <tr key={m.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(m.occurred_at)}</td>
                  <td className="px-4 py-3 font-medium">{productMap.get(m.product_id) ?? "—"}</td>
                  <td className="px-4 py-3">
                    <Badge variant="outline" className={cn("font-normal", TYPE_CLASS[m.movement_type])}>
                      {STOCK_MOVEMENT_TYPE_LABELS[m.movement_type] ?? m.movement_type}
                    </Badge>
                  </td>
                  <td className="px-4 py-3"><QuantityCell type={m.movement_type} quantity={m.quantity} /></td>
                  <td className="px-4 py-3">{m.unit_cost ? formatBRLFromDecimal(m.unit_cost) : "—"}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{m.source_type ?? "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{m.notes ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canWrite && (
        <RegisterMovementDialog open={registerOpen} onOpenChange={setRegisterOpen} onSaved={load} products={products} />
      )}
    </div>
  )
}
