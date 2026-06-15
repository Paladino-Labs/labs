"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, Lock, Unlock } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { FinancialAccount, FinancialMovement, Reconciliation, CashCount } from "@/types"
import { MOVEMENT_TYPE_LABELS, CASH_COUNT_RESOLUTION_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ReconciliationBadge } from "@/components/FsmBadge"
import { MoneyInput } from "@/components/MoneyInput"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

function discrepancyClass(value: string): string {
  if (value.startsWith("-")) return "text-destructive"
  if (parseFloat(value) === 0) return "text-success"
  return "text-amber-600 dark:text-amber-400"
}

/* ------------------------- Tab: Conciliação bancária ------------------------- */
function ReconciliationTab({ accounts, canWrite }: { accounts: FinancialAccount[]; canWrite: boolean }) {
  const [accountId, setAccountId] = useState("")
  const [recon, setRecon] = useState<Reconciliation | null>(null)
  const [unreconciled, setUnreconciled] = useState<FinancialMovement[]>([])
  const [loading, setLoading] = useState(false)
  const [busy, setBusy] = useState(false)
  const [closeOpen, setCloseOpen] = useState(false)

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.account_id, a.name])), [accounts])

  const loadUnreconciled = useCallback(async (accId: string) => {
    setLoading(true)
    try {
      setUnreconciled(await api.get<FinancialMovement[]>(`/financial/movements/unreconciled?account_id=${accId}`))
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao carregar pendências")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { setRecon(null); setUnreconciled([]) }, [accountId])

  async function handleOpen() {
    if (!accountId) return
    setBusy(true)
    try {
      const res = await api.post<Reconciliation>("/financial/reconciliation", { account_id: accountId })
      setRecon(res)
      await loadUnreconciled(accountId)
      toast.success("Conciliação aberta")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao abrir conciliação")
    } finally {
      setBusy(false)
    }
  }

  async function handleReconcile(movementId: string) {
    if (!recon) return
    setBusy(true)
    try {
      await api.post(`/financial/movements/${movementId}/reconcile`, { reconciliation_id: recon.reconciliation_id })
      toast.success("Movimento conciliado")
      setUnreconciled((prev) => prev.filter((m) => m.movement_id !== movementId))
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao conciliar movimento")
    } finally {
      setBusy(false)
    }
  }

  async function handleClose() {
    if (!recon) return
    setBusy(true)
    try {
      await api.put(`/financial/reconciliation/${recon.reconciliation_id}/close`, {})
      toast.success("Conciliação fechada")
      setRecon(null); setUnreconciled([]); setCloseOpen(false)
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao fechar conciliação")
    } finally {
      setBusy(false)
    }
  }

  const hasOpen = !!recon

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border p-4">
        <div className="space-y-1">
          <Label>Conta</Label>
          <Select value={accountId || "none"} onValueChange={(v) => v && setAccountId(v === "none" ? "" : v)}>
            <SelectTrigger className="w-56">
              <SelectValue>{accountId ? (accountMap.get(accountId) ?? "—") : "Selecione"}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        {canWrite && accountId && (
          hasOpen ? (
            <>
              <ReconciliationBadge status={recon.status} />
              <span className="text-xs text-muted-foreground">Aberta em {formatDateTime(recon.opened_at)}</span>
              <Button variant="outline" onClick={() => setCloseOpen(true)} disabled={busy}>
                <Lock className="h-4 w-4" /> Fechar conciliação
              </Button>
            </>
          ) : (
            <>
              <Button onClick={handleOpen} disabled={busy}>
                <Unlock className="h-4 w-4" /> Abrir conciliação
              </Button>
              <Tooltip>
                <TooltipTrigger render={<span tabIndex={0} />}>
                  <Button variant="outline" disabled><Lock className="h-4 w-4" /> Fechar</Button>
                </TooltipTrigger>
                <TooltipContent>Abra uma conciliação primeiro.</TooltipContent>
              </Tooltip>
            </>
          )
        )}
      </div>

      {!accountId ? (
        <EmptyState title="Selecione uma conta" description="Escolha uma conta para começar." />
      ) : !hasOpen ? (
        <EmptyState icon={<Unlock size={28} strokeWidth={1.5} />} title="Sem conciliação aberta" description="Abra uma conciliação para listar pendências." />
      ) : loading ? (
        <Skeleton className="h-40 w-full" />
      ) : unreconciled.length === 0 ? (
        <EmptyState icon={<CheckCircle2 size={28} strokeWidth={1.5} />} title="Tudo conciliado" description="Você pode fechar a conciliação." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Origem</th>
                <th className="px-4 py-3 text-right font-medium">Ação</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {unreconciled.map((m) => (
                <tr key={m.movement_id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(m.occurred_at)}</td>
                  <td className="px-4 py-3">{MOVEMENT_TYPE_LABELS[m.type] ?? m.type}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(m.amount)}</td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">{m.source_type}</td>
                  <td className="px-4 py-3 text-right">
                    <Button size="sm" variant="ghost" disabled={busy} onClick={() => handleReconcile(m.movement_id)}>
                      <CheckCircle2 className="h-3.5 w-3.5" /> Marcar conciliado
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={closeOpen} onOpenChange={setCloseOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Fechar conciliação?</DialogTitle>
            <DialogDescription>Após fechar, nenhum movimento poderá ser conciliado nesta janela.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button onClick={handleClose} disabled={busy}>Fechar conciliação</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* --------------------------- Tab: Contagem de caixa --------------------------- */
function CashCountTab({ accounts }: { accounts: FinancialAccount[] }) {
  const [counts, setCounts] = useState<CashCount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState(false)

  const [accountId, setAccountId] = useState("")
  const [counted, setCounted] = useState("")
  const [resolution, setResolution] = useState("NO_ADJUSTMENT")
  const [notes, setNotes] = useState("")
  const [busy, setBusy] = useState(false)

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.account_id, a.name])), [accounts])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setCounts(await api.get<CashCount[]>("/financial/cash-counts"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    if (open) { setAccountId(""); setCounted(""); setResolution("NO_ADJUSTMENT"); setNotes("") }
  }, [open])

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api.post("/financial/cash-counts", {
        account_id: accountId, counted_amount: counted, resolution, notes: notes || null,
      })
      toast.success("Contagem registrada")
      setOpen(false); load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao registrar contagem (notas obrigatórias se houver divergência com ajuste)")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setOpen(true)}>+ Registrar contagem</Button>
      </div>

      {loading ? (
        <Skeleton className="h-40 w-full" />
      ) : error ? (
        <EmptyState message={error} />
      ) : counts.length === 0 ? (
        <EmptyState title="Nenhuma contagem" description="Registre a primeira contagem de caixa." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Conta</th>
                <th className="px-4 py-3 text-right font-medium">Esperado</th>
                <th className="px-4 py-3 text-right font-medium">Contado</th>
                <th className="px-4 py-3 text-right font-medium">Divergência</th>
                <th className="px-4 py-3 text-left font-medium">Resolução</th>
                <th className="px-4 py-3 text-left font-medium">Notas</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {counts.map((c) => (
                <tr key={c.cash_count_id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(c.created_at)}</td>
                  <td className="px-4 py-3 font-medium">{accountMap.get(c.account_id) ?? "—"}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(c.expected_amount)}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(c.counted_amount)}</td>
                  <td className={cn("px-4 py-3 text-right font-medium", discrepancyClass(c.discrepancy))}>
                    {formatBRLFromDecimal(c.discrepancy)}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{CASH_COUNT_RESOLUTION_LABELS[c.resolution] ?? c.resolution}</td>
                  <td className="px-4 py-3 text-muted-foreground">{c.notes ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar contagem de caixa</DialogTitle>
            <DialogDescription>A divergência é calculada pela API.</DialogDescription>
          </DialogHeader>
          <form onSubmit={handleRegister} className="space-y-4 py-1">
            <div className="space-y-1">
              <Label>Conta</Label>
              <Select value={accountId || "none"} onValueChange={(v) => v && setAccountId(v === "none" ? "" : v)}>
                <SelectTrigger className="w-full"><SelectValue>{accountId ? (accountMap.get(accountId) ?? "—") : "Selecione"}</SelectValue></SelectTrigger>
                <SelectContent>{accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="cc-counted">Valor contado</Label>
              <MoneyInput id="cc-counted" value={counted} onChange={setCounted} />
            </div>
            <div className="space-y-1.5">
              <Label>Resolução</Label>
              <div className="flex gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="resolution" checked={resolution === "NO_ADJUSTMENT"}
                    onChange={() => setResolution("NO_ADJUSTMENT")} className="accent-primary" /> Sem ajuste
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="radio" name="resolution" checked={resolution === "ADJUSTED"}
                    onChange={() => setResolution("ADJUSTED")} className="accent-primary" /> Com ajuste
                </label>
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="cc-notes">Notas</Label>
              <Textarea id="cc-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Justifique a divergência" />
            </div>
            <DialogFooter>
              <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
              <Button type="submit" disabled={busy || !accountId || !counted}>Registrar</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* --------------------------------- Página --------------------------------- */
export default function ConciliacaoPage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN"
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])

  useEffect(() => {
    api.get<FinancialAccount[]>("/financial/accounts").then(setAccounts).catch(() => {})
  }, [])

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Conciliação" description="Conciliação bancária sequencial e contagem de caixa." />
      <Tabs defaultValue="bancaria">
        <TabsList>
          <TabsTrigger value="bancaria">Conciliação bancária</TabsTrigger>
          <TabsTrigger value="caixa">Contagem de caixa</TabsTrigger>
        </TabsList>
        <TabsContent value="bancaria">
          <ReconciliationTab accounts={accounts} canWrite={canWrite} />
        </TabsContent>
        <TabsContent value="caixa">
          <CashCountTab accounts={accounts} />
        </TabsContent>
      </Tabs>
    </div>
  )
}
