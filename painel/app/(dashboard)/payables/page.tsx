"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { ListChecks, Package, XCircle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatBRLFromDecimal, formatDateShort, formatDateTime } from "@/lib/utils"
import type { Payable, PayableInstallment, Supplier, FinancialAccount } from "@/types"
import { CLOSING_METHOD_LABELS, PAYABLE_STATUS_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { PayableBadge, InstallmentBadge } from "@/components/FsmBadge"
import { MoneyInput } from "@/components/MoneyInput"
import { DateTimePicker } from "@/components/DateTimePicker"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

const STATUS_FILTER: Record<string, string> = {
  all: "Todos", OPEN: "Em aberto", PARTIALLY_PAID: "Parcial", PAID: "Paga", CANCELLED: "Cancelada",
}

interface InstallmentDraft { amount: string; due_date: string }

/* -------------------------------- Criar -------------------------------- */
function CreatePayableDialog({ open, onOpenChange, onCreated, suppliers }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: () => void
  suppliers: Supplier[]
}) {
  const [description, setDescription] = useState("")
  const [totalAmount, setTotalAmount] = useState("")
  const [supplierId, setSupplierId] = useState("none")
  const [dueDate, setDueDate] = useState("")
  const [closingMethod, setClosingMethod] = useState("CASH_AT_CREATION")
  const [installments, setInstallments] = useState<InstallmentDraft[]>([{ amount: "", due_date: "" }])
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setDescription(""); setTotalAmount(""); setSupplierId("none"); setDueDate("")
      setClosingMethod("CASH_AT_CREATION"); setInstallments([{ amount: "", due_date: "" }])
    }
  }, [open])

  function updateInst(i: number, patch: Partial<InstallmentDraft>) {
    setInstallments((prev) => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)))
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        description: description.trim(),
        total_amount: totalAmount,
        supplier_id: supplierId === "none" ? null : supplierId,
        due_date: dueDate ? dueDate.slice(0, 10) : null,
        closing_method: closingMethod,
      }
      if (closingMethod === "INSTALLMENTS") {
        body.installments = installments.map((it) => ({
          amount: it.amount,
          due_date: it.due_date ? it.due_date.slice(0, 10) : null,
        }))
      }
      await api.post("/payables/", body)
      toast.success("Conta a pagar criada")
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar conta a pagar")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Nova conta a pagar</DialogTitle></DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="pay-desc">Descrição</Label>
            <Input id="pay-desc" value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={255} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pay-total">Valor total</Label>
              <MoneyInput id="pay-total" value={totalAmount} onChange={setTotalAmount} />
            </div>
            <div className="space-y-1">
              <Label>Fornecedor</Label>
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
          </div>
          <div className="space-y-1">
            <Label htmlFor="pay-due">Vencimento</Label>
            <DateTimePicker id="pay-due" value={dueDate} onChange={setDueDate} />
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
          {closingMethod === "INSTALLMENTS" && (
            <div className="space-y-2">
              <Label>Parcelas</Label>
              {installments.map((inst, i) => (
                <div key={i} className="flex items-end gap-2">
                  <div className="w-32"><MoneyInput value={inst.amount} onChange={(v) => updateInst(i, { amount: v })} /></div>
                  <div className="flex-1"><DateTimePicker value={inst.due_date} onChange={(v) => updateInst(i, { due_date: v })} /></div>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm"
                onClick={() => setInstallments((prev) => [...prev, { amount: "", due_date: "" }])}>
                + Adicionar parcela
              </Button>
            </div>
          )}
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !description.trim() || !totalAmount}>{saving ? "Criando…" : "Criar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ----------------------- Sheet de parcelas + pagar ----------------------- */
function InstallmentsSheet({ payable, onClose, onChanged, accounts, canWrite }: {
  payable: Payable | null
  onClose: () => void
  onChanged: () => void
  accounts: FinancialAccount[]
  canWrite: boolean
}) {
  const [installments, setInstallments] = useState<PayableInstallment[]>([])
  const [loading, setLoading] = useState(false)
  const [payTarget, setPayTarget] = useState<PayableInstallment | null>(null)
  const [accountId, setAccountId] = useState("none")
  const [busy, setBusy] = useState(false)

  const loadInstallments = useCallback(async (id: string) => {
    setLoading(true)
    try {
      setInstallments(await api.get<PayableInstallment[]>(`/payables/${id}/installments`))
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao carregar parcelas")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (payable) loadInstallments(payable.id)
  }, [payable, loadInstallments])

  async function handlePay() {
    if (!payable || !payTarget) return
    setBusy(true)
    try {
      await api.patch(`/payables/${payable.id}/installments/${payTarget.id}/pay`,
        accountId === "none" ? {} : { account_id: accountId })
      toast.success("Parcela paga")
      setPayTarget(null); setAccountId("none")
      await loadInstallments(payable.id)
      onChanged()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao pagar parcela")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Sheet open={!!payable} onOpenChange={(v) => !v && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Parcelas</SheetTitle>
          <SheetDescription>{payable?.description}</SheetDescription>
        </SheetHeader>
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : installments.length === 0 ? (
          <EmptyState message="Nenhuma parcela." />
        ) : (
          <table className="w-full text-sm">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-2 text-left font-medium">Nº</th>
                <th className="py-2 text-left font-medium">Valor</th>
                <th className="py-2 text-left font-medium">Vencimento</th>
                <th className="py-2 text-left font-medium">Status</th>
                <th className="py-2 text-left font-medium">Pago em</th>
                {canWrite && <th className="py-2 text-right font-medium">Ação</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {installments.map((inst) => (
                <tr key={inst.id}>
                  <td className="py-2">{inst.installment_number}</td>
                  <td className="py-2">{formatBRLFromDecimal(inst.amount)}</td>
                  <td className="py-2 text-muted-foreground">{formatDateShort(inst.due_date)}</td>
                  <td className="py-2"><InstallmentBadge status={inst.status} /></td>
                  <td className="py-2 text-xs text-muted-foreground">{inst.paid_at ? formatDateTime(inst.paid_at) : "—"}</td>
                  {canWrite && (
                    <td className="py-2 text-right">
                      {inst.status === "OPEN" && (
                        <Button size="sm" variant="ghost" onClick={() => { setPayTarget(inst); setAccountId("none") }}>
                          Pagar
                        </Button>
                      )}
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <Dialog open={!!payTarget} onOpenChange={(v) => !v && setPayTarget(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Pagar parcela {payTarget?.installment_number}</DialogTitle>
              <DialogDescription>{payTarget && formatBRLFromDecimal(payTarget.amount)} — debitar de uma conta (opcional).</DialogDescription>
            </DialogHeader>
            <div className="space-y-1 py-1">
              <Label>Conta</Label>
              <Select value={accountId} onValueChange={(v) => v && setAccountId(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue>{accountId === "none" ? "Não debitar de conta" : (accounts.find((a) => a.account_id === accountId)?.name ?? "—")}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Não debitar de conta</SelectItem>
                  {accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <DialogFooter>
              <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
              <Button onClick={handlePay} disabled={busy}>Confirmar pagamento</Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </SheetContent>
    </Sheet>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function PayablesPage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"

  const [payables, setPayables] = useState<Payable[]>([])
  const [suppliers, setSuppliers] = useState<Supplier[]>([])
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [sheetPayable, setSheetPayable] = useState<Payable | null>(null)
  const [cancelTarget, setCancelTarget] = useState<Payable | null>(null)
  const [cancelReason, setCancelReason] = useState("")
  const [busy, setBusy] = useState<string | null>(null)
  const [highlightId, setHighlightId] = useState<string | null>(null)

  const [statusFilter, setStatusFilter] = useState("all")
  const [supplierFilter, setSupplierFilter] = useState("all")
  const [dueFrom, setDueFrom] = useState("")
  const [dueTo, setDueTo] = useState("")

  const supplierMap = useMemo(() => new Map(suppliers.map((s) => [s.id, s.name])), [suppliers])

  useEffect(() => {
    api.get<Supplier[]>("/suppliers/").then(setSuppliers).catch(() => {})
    if (canWrite) api.get<FinancialAccount[]>("/financial/accounts").then(setAccounts).catch(() => {})
    // Destaque ao chegar de "Receber pedido"
    const params = new URLSearchParams(window.location.search)
    const pid = params.get("payable_id")
    if (pid) setHighlightId(pid)
  }, [canWrite])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (supplierFilter !== "all") params.set("supplier_id", supplierFilter)
    if (dueFrom) params.set("due_date_from", dueFrom)
    if (dueTo) params.set("due_date_to", dueTo)
    const q = params.toString()
    try {
      setPayables(await api.get<Payable[]>(`/payables/${q ? `?${q}` : ""}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, supplierFilter, dueFrom, dueTo])

  useEffect(() => { load() }, [load])

  async function handleCancel() {
    if (!cancelTarget || !cancelReason.trim()) return
    setBusy(cancelTarget.id)
    try {
      await api.patch(`/payables/${cancelTarget.id}/cancel`, { reason: cancelReason.trim() })
      toast.success("Conta a pagar cancelada")
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
      <PageHeader eyebrow="Financeiro" title="Contas a pagar" description="Payables com parcelas e pagamento por parcela.">
        {canWrite && <Button onClick={() => setCreateOpen(true)}>+ Nova conta</Button>}
      </PageHeader>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
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
          <Label htmlFor="pay-from">Venc. de</Label>
          <Input id="pay-from" type="date" value={dueFrom} onChange={(e) => setDueFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="pay-to">Até</Label>
          <Input id="pay-to" type="date" value={dueTo} onChange={(e) => setDueTo(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : payables.length === 0 ? (
        <EmptyState title="Nenhuma conta a pagar" description="Crie uma conta ou receba um pedido de fornecedor." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Descrição</th>
                <th className="px-4 py-3 text-left font-medium">Fornecedor</th>
                <th className="px-4 py-3 text-right font-medium">Total</th>
                <th className="px-4 py-3 text-right font-medium">Pago</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Vencimento</th>
                <th className="px-4 py-3 text-left font-medium">Fechamento</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {payables.map((p) => {
                const fromOrder = p.source_type === "SUPPLIER_ORDER"
                const canCancel = canWrite && p.status !== "PAID" && p.status !== "CANCELLED"
                return (
                  <tr key={p.id} className={highlightId === p.id ? "bg-primary/5" : "transition-colors hover:bg-muted/30"}>
                    <td className="px-4 py-3 font-medium">
                      <span className="flex items-center gap-2">
                        {fromOrder && <Package className="h-3.5 w-3.5 text-muted-foreground shrink-0" aria-label="Pedido de estoque" />}
                        {p.description}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{p.supplier_id ? (supplierMap.get(p.supplier_id) ?? "—") : "—"}</td>
                    <td className="px-4 py-3 text-right">{formatBRLFromDecimal(p.total_amount)}</td>
                    <td className="px-4 py-3 text-right">{formatBRLFromDecimal(p.paid_amount)}</td>
                    <td className="px-4 py-3"><PayableBadge status={p.status} /></td>
                    <td className="px-4 py-3 text-muted-foreground">{formatDateShort(p.due_date)}</td>
                    <td className="px-4 py-3 text-muted-foreground">{CLOSING_METHOD_LABELS[p.closing_method] ?? p.closing_method}</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button size="sm" variant="ghost" onClick={() => setSheetPayable(p)}>
                          <ListChecks className="h-3.5 w-3.5" /> Parcelas
                        </Button>
                        {canCancel && (
                          <Button size="icon-sm" variant="ghost" className="text-destructive" disabled={busy === p.id}
                            onClick={() => { setCancelTarget(p); setCancelReason("") }} aria-label="Cancelar">
                            <XCircle className="h-4 w-4" />
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

      <CreatePayableDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={load} suppliers={suppliers} />
      <InstallmentsSheet payable={sheetPayable} onClose={() => setSheetPayable(null)} onChanged={load} accounts={accounts} canWrite={canWrite} />

      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar conta a pagar</DialogTitle>
            <DialogDescription>Informe o motivo do cancelamento de “{cancelTarget?.description}”.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1 py-1">
            <Label htmlFor="pay-cancel-reason">Motivo *</Label>
            <Textarea id="pay-cancel-reason" value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} rows={3} required />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleCancel} disabled={!cancelReason.trim() || busy === cancelTarget?.id}>
              Cancelar conta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
