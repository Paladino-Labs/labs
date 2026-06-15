"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Repeat, CheckCircle2, XCircle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatBRLFromDecimal, formatDateShort, formatDateTime } from "@/lib/utils"
import type { Expense, Supplier } from "@/types"
import {
  ENTRY_CATEGORY_LABELS,
  EXPENSE_CATEGORY_OPTIONS,
  RECURRENCE_FREQUENCY_LABELS,
} from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ExpenseBadge } from "@/components/FsmBadge"
import { MoneyInput } from "@/components/MoneyInput"
import { DateTimePicker } from "@/components/DateTimePicker"
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

const STATUS_FILTER: Record<string, string> = {
  all: "Todos", PENDENTE: "Pendente", PAGA: "Paga", CANCELLED: "Cancelada",
}

/* --------------------------------- Criar --------------------------------- */
function CreateExpenseDialog({ open, onOpenChange, onCreated, suppliers }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: () => void
  suppliers: Supplier[]
}) {
  const [description, setDescription] = useState("")
  const [amount, setAmount] = useState("")
  const [category, setCategory] = useState("DESPESA_OUTROS")
  const [dueDate, setDueDate] = useState("")
  const [supplierId, setSupplierId] = useState("none")
  const [recurrent, setRecurrent] = useState(false)
  const [frequency, setFrequency] = useState("MONTHLY")
  const [dayOfMonth, setDayOfMonth] = useState("1")
  const [endDate, setEndDate] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setDescription(""); setAmount(""); setCategory("DESPESA_OUTROS"); setDueDate("")
      setSupplierId("none"); setRecurrent(false); setFrequency("MONTHLY")
      setDayOfMonth("1"); setEndDate("")
    }
  }, [open])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/expenses/", {
        description: description.trim(),
        amount,
        category,
        due_date: dueDate ? dueDate.slice(0, 10) : null,
        supplier_id: supplierId === "none" ? null : supplierId,
        recurrence_rule: recurrent
          ? {
              frequency,
              day_of_month: parseInt(dayOfMonth, 10) || 1,
              end_date: endDate ? endDate.slice(0, 10) : null,
            }
          : null,
      })
      toast.success("Despesa lançada")
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao lançar despesa")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Nova despesa</DialogTitle>
          <DialogDescription>Valores em decimal — sem cálculo no cliente.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="ex-desc">Descrição</Label>
            <Input id="ex-desc" value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={255} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="ex-amount">Valor</Label>
              <MoneyInput id="ex-amount" value={amount} onChange={setAmount} />
            </div>
            <div className="space-y-1">
              <Label>Categoria</Label>
              <Select value={category} onValueChange={(v) => v && setCategory(v)}>
                <SelectTrigger className="w-full"><SelectValue>{ENTRY_CATEGORY_LABELS[category]}</SelectValue></SelectTrigger>
                <SelectContent>
                  {EXPENSE_CATEGORY_OPTIONS.map((c) => (
                    <SelectItem key={c} value={c}>{ENTRY_CATEGORY_LABELS[c]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="ex-due">Vencimento</Label>
            <DateTimePicker id="ex-due" value={dueDate} onChange={setDueDate} />
          </div>
          <div className="space-y-1">
            <Label>Fornecedor (opcional)</Label>
            <Select value={supplierId} onValueChange={(v) => v && setSupplierId(v)}>
              <SelectTrigger className="w-full">
                <SelectValue>
                  {supplierId === "none" ? "Sem fornecedor" : (suppliers.find((s) => s.id === supplierId)?.name ?? "—")}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Sem fornecedor</SelectItem>
                {suppliers.map((s) => (
                  <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-3 rounded-lg border border-border px-3 py-2">
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="ex-rec">Recorrente</Label>
                <p className="text-xs text-muted-foreground">Gera novas despesas automaticamente.</p>
              </div>
              <Switch id="ex-rec" checked={recurrent} onCheckedChange={setRecurrent} />
            </div>
            {recurrent && (
              <div className="grid grid-cols-3 gap-3 pt-1">
                <div className="space-y-1">
                  <Label>Frequência</Label>
                  <Select value={frequency} onValueChange={(v) => v && setFrequency(v)}>
                    <SelectTrigger className="w-full"><SelectValue>{RECURRENCE_FREQUENCY_LABELS[frequency]}</SelectValue></SelectTrigger>
                    <SelectContent>
                      {Object.keys(RECURRENCE_FREQUENCY_LABELS).map((f) => (
                        <SelectItem key={f} value={f}>{RECURRENCE_FREQUENCY_LABELS[f]}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="ex-dom">Dia do mês</Label>
                  <Input id="ex-dom" type="number" min="1" max="31" value={dayOfMonth} onChange={(e) => setDayOfMonth(e.target.value)} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="ex-end">Fim (opcional)</Label>
                  <DateTimePicker id="ex-end" value={endDate} onChange={setEndDate} />
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !description.trim() || !amount || !dueDate}>
              {saving ? "Lançando…" : "Lançar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function ExpensesPage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"

  const [expenses, setExpenses] = useState<Expense[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)

  const [statusFilter, setStatusFilter] = useState("all")
  const [categoryFilter, setCategoryFilter] = useState("all")
  const [supplierFilter, setSupplierFilter] = useState("all")
  const [dueFrom, setDueFrom] = useState("")
  const [dueTo, setDueTo] = useState("")

  const [payTarget, setPayTarget] = useState<Expense | null>(null)
  const [payAmount, setPayAmount] = useState("")
  const [cancelTarget, setCancelTarget] = useState<Expense | null>(null)
  const [cancelReason, setCancelReason] = useState("")

  const supplierMap = useMemo(() => new Map(suppliers.map((s) => [s.id, s.name])), [suppliers])

  useEffect(() => {
    api.get<Supplier[]>("/suppliers/").then(setSuppliers).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (categoryFilter !== "all") params.set("category", categoryFilter)
    if (supplierFilter !== "all") params.set("supplier_id", supplierFilter)
    if (dueFrom) params.set("due_date_from", dueFrom)
    if (dueTo) params.set("due_date_to", dueTo)
    const q = params.toString()
    try {
      setExpenses(await api.get<Expense[]>(`/expenses/${q ? `?${q}` : ""}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, categoryFilter, supplierFilter, dueFrom, dueTo])

  useEffect(() => { load() }, [load])

  async function handlePay() {
    if (!payTarget) return
    setBusy(payTarget.id)
    try {
      await api.patch(`/expenses/${payTarget.id}/pay`, payAmount ? { paid_amount: payAmount } : {})
      toast.success("Despesa paga")
      setPayTarget(null); setPayAmount("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao pagar")
    } finally {
      setBusy(null)
    }
  }

  async function handleCancel() {
    if (!cancelTarget || !cancelReason.trim()) return
    setBusy(cancelTarget.id)
    try {
      await api.patch(`/expenses/${cancelTarget.id}/cancel`, { reason: cancelReason.trim() })
      toast.success("Despesa cancelada")
      setCancelTarget(null); setCancelReason("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao cancelar")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Despesas" description="Despesas lançadas, recorrentes e baixas.">
        {canWrite && <Button onClick={() => setCreateOpen(true)}>+ Nova despesa</Button>}
      </PageHeader>

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-full"><SelectValue>{STATUS_FILTER[statusFilter]}</SelectValue></SelectTrigger>
            <SelectContent>
              {Object.entries(STATUS_FILTER).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Categoria</Label>
          <Select value={categoryFilter} onValueChange={(v) => v && setCategoryFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{categoryFilter === "all" ? "Todas" : ENTRY_CATEGORY_LABELS[categoryFilter]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              {EXPENSE_CATEGORY_OPTIONS.map((c) => <SelectItem key={c} value={c}>{ENTRY_CATEGORY_LABELS[c]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Fornecedor</Label>
          <Select value={supplierFilter} onValueChange={(v) => v && setSupplierFilter(v)}>
            <SelectTrigger className="w-full">
              <SelectValue>{supplierFilter === "all" ? "Todos" : (supplierMap.get(supplierFilter) ?? "—")}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {suppliers.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="ex-from">Venc. de</Label>
          <Input id="ex-from" type="date" value={dueFrom} onChange={(e) => setDueFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="ex-to">Venc. até</Label>
          <Input id="ex-to" type="date" value={dueTo} onChange={(e) => setDueTo(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : expenses.length === 0 ? (
        <EmptyState title="Nenhuma despesa" description="Lance a primeira despesa ou ajuste os filtros." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Descrição</th>
                <th className="px-4 py-3 text-left font-medium">Categoria</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Vencimento</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Fornecedor</th>
                <th className="px-4 py-3 text-left font-medium">Pago</th>
                {canWrite && <th className="px-4 py-3 text-right font-medium">Ações</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {expenses.map((ex) => {
                const isChild = !!ex.parent_expense_id
                const disabled = busy === ex.id
                return (
                  <tr key={ex.id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">
                      <span className="flex items-center gap-2">
                        {isChild && <Repeat className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-label="Despesa recorrente" />}
                        {ex.description}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{ENTRY_CATEGORY_LABELS[ex.category] ?? ex.category}</td>
                    <td className="px-4 py-3 text-right">{formatBRLFromDecimal(ex.amount)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateShort(ex.due_date)}</td>
                    <td className="px-4 py-3"><ExpenseBadge status={ex.status} /></td>
                    <td className="px-4 py-3 text-muted-foreground">{ex.supplier_id ? (supplierMap.get(ex.supplier_id) ?? "—") : "—"}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {ex.status === "PAGA" && ex.paid_amount != null ? (
                        <>
                          <div>{formatBRLFromDecimal(ex.paid_amount)}</div>
                          {ex.paid_at && <div>{formatDateTime(ex.paid_at)}</div>}
                        </>
                      ) : "—"}
                    </td>
                    {canWrite && (
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-2">
                          {ex.status === "PENDENTE" && !isChild && (
                            <>
                              <Button size="sm" variant="ghost" disabled={disabled}
                                onClick={() => { setPayTarget(ex); setPayAmount("") }}>
                                <CheckCircle2 className="h-3.5 w-3.5" /> Pagar
                              </Button>
                              <Button size="sm" variant="ghost" className="text-destructive" disabled={disabled}
                                onClick={() => { setCancelTarget(ex); setCancelReason("") }}>
                                <XCircle className="h-3.5 w-3.5" /> Cancelar
                              </Button>
                            </>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <CreateExpenseDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={load} suppliers={suppliers} />

      {/* Pagar */}
      <Dialog open={!!payTarget} onOpenChange={(v) => !v && setPayTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Pagar despesa</DialogTitle>
            <DialogDescription>“{payTarget?.description}” — deixe em branco para pagar o valor integral.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1 py-1">
            <Label htmlFor="pay-amount">Valor pago (opcional)</Label>
            <MoneyInput id="pay-amount" value={payAmount} onChange={setPayAmount}
              placeholder={payTarget ? payTarget.amount : "0,00"} />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button onClick={handlePay} disabled={busy === payTarget?.id}>Confirmar pagamento</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancelar */}
      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar despesa</DialogTitle>
            <DialogDescription>Informe o motivo do cancelamento de “{cancelTarget?.description}”.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1 py-1">
            <Label htmlFor="cancel-reason">Motivo *</Label>
            <Textarea id="cancel-reason" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} rows={3} required />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleCancel} disabled={!cancelReason.trim() || busy === cancelTarget?.id}>
              Cancelar despesa
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
