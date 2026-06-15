"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { ArrowLeftRight, Calculator, Landmark, Wallet } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { FinancialAccount, Transfer, FinancialMovement, FinancialSettings } from "@/types"
import {
  ACCOUNT_TYPE_LABELS, MOVEMENT_TYPE_LABELS,
  ADJUSTMENT_CATEGORY_OPTIONS, ENTRY_CATEGORY_LABELS,
} from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { TransferBadge } from "@/components/FsmBadge"
import { MoneyInput } from "@/components/MoneyInput"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

/* ------------------------------ Nova conta ------------------------------ */
function NewAccountDialog({ open, onOpenChange, onSaved }: {
  open: boolean; onOpenChange: (v: boolean) => void; onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [type, setType] = useState("BANK")
  const [provider, setProvider] = useState("")
  const [externalRef, setExternalRef] = useState("")
  const [isDefault, setIsDefault] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) { setName(""); setType("BANK"); setProvider(""); setExternalRef(""); setIsDefault(false) }
  }, [open])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/financial/accounts", {
        name: name.trim(), type, provider: provider || null,
        external_ref: externalRef || null, is_default_inflow: isDefault,
      })
      toast.success("Conta criada")
      onOpenChange(false); onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar conta")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Nova conta</DialogTitle></DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="acc-name">Nome</Label>
            <Input id="acc-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label>Tipo</Label>
            <Select value={type} onValueChange={(v) => v && setType(v)}>
              <SelectTrigger className="w-full"><SelectValue>{ACCOUNT_TYPE_LABELS[type]}</SelectValue></SelectTrigger>
              <SelectContent>
                {Object.entries(ACCOUNT_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="acc-prov">Provider</Label>
              <Input id="acc-prov" value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="Stone, Itaú…" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="acc-ref">Ref. externa</Label>
              <Input id="acc-ref" value={externalRef} onChange={(e) => setExternalRef(e.target.value)} />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <Label htmlFor="acc-default">Conta padrão de entrada</Label>
            <Switch id="acc-default" checked={isDefault} onCheckedChange={setIsDefault} />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !name.trim()}>{saving ? "Criando…" : "Criar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ------------------------------ Transferir ------------------------------ */
function TransferDialog({ open, onOpenChange, onSaved, accounts }: {
  open: boolean; onOpenChange: (v: boolean) => void; onSaved: () => void; accounts: FinancialAccount[]
}) {
  const [fromId, setFromId] = useState("")
  const [toId, setToId] = useState("")
  const [amount, setAmount] = useState("")
  const [notes, setNotes] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => { if (open) { setFromId(""); setToId(""); setAmount(""); setNotes("") } }, [open])

  const valid = fromId && toId && fromId !== toId && amount

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/financial/transfers", { from_account_id: fromId, to_account_id: toId, amount, notes: notes || null })
      toast.success("Transferência solicitada")
      onOpenChange(false); onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao transferir")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Transferir entre contas</DialogTitle></DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label>Origem</Label>
            <Select value={fromId || "none"} onValueChange={(v) => v && setFromId(v === "none" ? "" : v)}>
              <SelectTrigger className="w-full"><SelectValue>{fromId ? (accounts.find((a) => a.account_id === fromId)?.name ?? "—") : "Selecione"}</SelectValue></SelectTrigger>
              <SelectContent>{accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Destino</Label>
            <Select value={toId || "none"} onValueChange={(v) => v && setToId(v === "none" ? "" : v)}>
              <SelectTrigger className="w-full"><SelectValue>{toId ? (accounts.find((a) => a.account_id === toId)?.name ?? "—") : "Selecione"}</SelectValue></SelectTrigger>
              <SelectContent>
                {accounts.filter((a) => a.account_id !== fromId).map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
              </SelectContent>
            </Select>
            {fromId && toId && fromId === toId && <p className="text-xs text-destructive">Origem e destino devem ser diferentes.</p>}
          </div>
          <div className="space-y-1">
            <Label htmlFor="tr-amount">Valor</Label>
            <MoneyInput id="tr-amount" value={amount} onChange={setAmount} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="tr-notes">Notas</Label>
            <Textarea id="tr-notes" value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !valid}>{saving ? "Transferindo…" : "Confirmar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* --------------------------- Ajuste manual --------------------------- */
function ManualAdjustmentDialog({ open, onOpenChange, onSaved, accounts }: {
  open: boolean; onOpenChange: (v: boolean) => void; onSaved: () => void; accounts: FinancialAccount[]
}) {
  const [amount, setAmount] = useState("")
  const [direction, setDirection] = useState("ADDS")
  const [category, setCategory] = useState("AJUSTE_OUTROS")
  const [accountId, setAccountId] = useState("")
  const [reason, setReason] = useState("")
  const [confirmed, setConfirmed] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) { setAmount(""); setDirection("ADDS"); setCategory("AJUSTE_OUTROS"); setAccountId(""); setReason(""); setConfirmed(false) }
  }, [open])

  const valid = amount && accountId && reason.trim() && confirmed

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/financial/manual-adjustment", {
        amount, direction, category, account_id: accountId, reason: reason.trim(),
      })
      toast.success("Ajuste registrado")
      onOpenChange(false); onSaved()
    } catch (err: unknown) {
      const e2 = err as { status?: number; message?: string }
      if (e2.status === 403) toast.error("Ação não habilitada para este tenant")
      else toast.error(e2.message ?? "Erro ao registrar ajuste")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Ajuste manual</DialogTitle>
          <DialogDescription>Operação sensível — gravada como Entry AJUSTE.</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="adj-amount">Valor</Label>
            <MoneyInput id="adj-amount" value={amount} onChange={setAmount} />
          </div>
          <div className="space-y-1.5">
            <Label>Direção</Label>
            <div className="flex gap-6">
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name="direction" value="ADDS" checked={direction === "ADDS"}
                  onChange={() => setDirection("ADDS")} className="accent-primary" /> Entrada
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input type="radio" name="direction" value="SUBTRACTS" checked={direction === "SUBTRACTS"}
                  onChange={() => setDirection("SUBTRACTS")} className="accent-primary" /> Saída
              </label>
            </div>
          </div>
          <div className="space-y-1">
            <Label>Categoria</Label>
            <Select value={category} onValueChange={(v) => v && setCategory(v)}>
              <SelectTrigger className="w-full"><SelectValue>{ENTRY_CATEGORY_LABELS[category]}</SelectValue></SelectTrigger>
              <SelectContent>
                {ADJUSTMENT_CATEGORY_OPTIONS.map((c) => <SelectItem key={c} value={c}>{ENTRY_CATEGORY_LABELS[c]}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Conta</Label>
            <Select value={accountId || "none"} onValueChange={(v) => v && setAccountId(v === "none" ? "" : v)}>
              <SelectTrigger className="w-full"><SelectValue>{accountId ? (accounts.find((a) => a.account_id === accountId)?.name ?? "—") : "Selecione"}</SelectValue></SelectTrigger>
              <SelectContent>{accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="adj-reason">Motivo *</Label>
            <Textarea id="adj-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} required />
          </div>
          <div className="flex items-center justify-between rounded-lg border border-destructive/40 bg-destructive/5 px-3 py-2">
            <Label htmlFor="adj-confirm">Confirmo que este ajuste é definitivo</Label>
            <Switch id="adj-confirm" checked={confirmed} onCheckedChange={setConfirmed} />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" variant="destructive" disabled={saving || !valid}>{saving ? "Registrando…" : "Confirmar ajuste"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* --------------------------------- Página --------------------------------- */
export default function ContasPage() {
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])
  const [balances, setBalances] = useState<Record<string, string>>({})
  const [settings, setSettings] = useState<FinancialSettings | null>(null)
  const [transfers, setTransfers] = useState<Transfer[]>([])
  const [movements, setMovements] = useState<FinancialMovement[]>([])
  const [movAccount, setMovAccount] = useState("all")
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [newOpen, setNewOpen] = useState(false)
  const [transferOpen, setTransferOpen] = useState(false)
  const [adjustOpen, setAdjustOpen] = useState(false)

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.account_id, a.name])), [accounts])

  const loadAccounts = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const accs = await api.get<FinancialAccount[]>("/financial/accounts")
      setAccounts(accs)
      // Saldo por conta (endpoint separado)
      const entries = await Promise.all(accs.map(async (a) => {
        try {
          const b = await api.get<{ balance: string }>(`/financial/accounts/${a.account_id}/balance`)
          return [a.account_id, b.balance] as const
        } catch { return [a.account_id, ""] as const }
      }))
      setBalances(Object.fromEntries(entries))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadAccounts()
    api.get<FinancialSettings>("/financial/settings").then(setSettings).catch(() => {})
    api.get<Transfer[]>("/financial/transfers").then(setTransfers).catch(() => {})
  }, [loadAccounts])

  const loadTransfers = useCallback(() => {
    api.get<Transfer[]>("/financial/transfers").then(setTransfers).catch(() => {})
  }, [])

  useEffect(() => {
    const q = movAccount !== "all" ? `?account_id=${movAccount}` : ""
    api.get<FinancialMovement[]>(`/financial/movements${q}`).then(setMovements).catch(() => {})
  }, [movAccount])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Financeiro"
        title="Contas"
        description={settings ? `Provedor: ${settings.payment_provider ?? "—"} · ${settings.accounts_count} contas` : "Contas, saldos e transferências."}
      >
        <Button onClick={() => setNewOpen(true)}>+ Nova conta</Button>
      </PageHeader>

      <Tabs defaultValue="contas">
        <TabsList>
          <TabsTrigger value="contas"><Landmark className="mr-1.5 inline h-4 w-4" />Contas</TabsTrigger>
          <TabsTrigger value="transferencias"><ArrowLeftRight className="mr-1.5 inline h-4 w-4" />Transferências</TabsTrigger>
          <TabsTrigger value="movimentos"><Wallet className="mr-1.5 inline h-4 w-4" />Movimentos</TabsTrigger>
          <TabsTrigger value="ajuste"><Calculator className="mr-1.5 inline h-4 w-4" />Ajuste manual</TabsTrigger>
        </TabsList>

        {/* Contas */}
        <TabsContent value="contas">
          {loading ? (
            <Skeleton className="h-48 w-full" />
          ) : error ? (
            <ErrorState message={error} onRetry={loadAccounts} />
          ) : accounts.length === 0 ? (
            <EmptyState title="Nenhuma conta" description="Crie a primeira conta financeira." />
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {accounts.map((a) => (
                <Card key={a.account_id}>
                  <CardContent className="p-5">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{ACCOUNT_TYPE_LABELS[a.type] ?? a.type}</p>
                      <div className="flex items-center gap-1.5">
                        {a.is_default_inflow && (
                          <Badge variant="outline" className="font-normal bg-primary/10 text-primary border-primary/30">Padrão</Badge>
                        )}
                        <ActiveBadge active={a.status === "ACTIVE"} />
                      </div>
                    </div>
                    <p className="mt-1 font-display text-2xl tracking-wide">{a.name}</p>
                    {(a.provider || a.external_ref) && (
                      <p className="text-xs text-muted-foreground">{[a.provider, a.external_ref].filter(Boolean).join(" · ")}</p>
                    )}
                    <p className="mt-3 font-display text-3xl tracking-tight">{formatBRLFromDecimal(balances[a.account_id])}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        {/* Transferências */}
        <TabsContent value="transferencias">
          <div className="mb-4 flex justify-end">
            <Button variant="outline" onClick={() => setTransferOpen(true)}>
              <ArrowLeftRight className="h-4 w-4" /> Transferir
            </Button>
          </div>
          {transfers.length === 0 ? (
            <EmptyState title="Nenhuma transferência" description="As transferências entre contas aparecem aqui." />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Origem → Destino</th>
                    <th className="px-4 py-3 text-right font-medium">Valor</th>
                    <th className="px-4 py-3 text-left font-medium">Status</th>
                    <th className="px-4 py-3 text-left font-medium">Solicitada</th>
                    <th className="px-4 py-3 text-left font-medium">Concluída / Falha</th>
                    <th className="px-4 py-3 text-left font-medium">Motivo</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {transfers.map((t) => (
                    <tr key={t.transfer_id} className="transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 font-medium">
                        {(accountMap.get(t.from_account_id) ?? "—")} → {(accountMap.get(t.to_account_id) ?? "—")}
                      </td>
                      <td className="px-4 py-3 text-right">{formatBRLFromDecimal(t.amount)}</td>
                      <td className="px-4 py-3"><TransferBadge status={t.status} /></td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(t.requested_at)}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        {t.completed_at ? formatDateTime(t.completed_at) : t.failed_at ? formatDateTime(t.failed_at) : "—"}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{t.failure_reason ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        {/* Movimentos */}
        <TabsContent value="movimentos">
          <div className="mb-4 max-w-xs space-y-1">
            <Label>Conta</Label>
            <Select value={movAccount} onValueChange={(v) => v && setMovAccount(v)}>
              <SelectTrigger className="w-full">
                <SelectValue>{movAccount === "all" ? "Todas" : (accountMap.get(movAccount) ?? "—")}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                {accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {movements.length === 0 ? (
            <EmptyState message="Nenhum movimento para esta conta." />
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Data</th>
                    <th className="px-4 py-3 text-left font-medium">Conta</th>
                    <th className="px-4 py-3 text-left font-medium">Tipo</th>
                    <th className="px-4 py-3 text-right font-medium">Valor</th>
                    <th className="px-4 py-3 text-left font-medium">Origem</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {movements.map((m) => (
                    <tr key={m.movement_id} className="transition-colors hover:bg-muted/30">
                      <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(m.occurred_at)}</td>
                      <td className="px-4 py-3">{accountMap.get(m.account_id) ?? "—"}</td>
                      <td className="px-4 py-3 text-muted-foreground">{MOVEMENT_TYPE_LABELS[m.type] ?? m.type}</td>
                      <td className="px-4 py-3 text-right">{formatBRLFromDecimal(m.amount)}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">{m.source_type}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </TabsContent>

        {/* Ajuste manual */}
        <TabsContent value="ajuste">
          <EmptyState
            icon={<Calculator size={28} strokeWidth={1.5} />}
            title="Ajuste manual"
            description="Lançamento sensível — exige confirmação dupla."
            action={<Button onClick={() => setAdjustOpen(true)}>Abrir Dialog de ajuste</Button>}
          />
        </TabsContent>
      </Tabs>

      <NewAccountDialog open={newOpen} onOpenChange={setNewOpen} onSaved={loadAccounts} />
      <TransferDialog open={transferOpen} onOpenChange={setTransferOpen} onSaved={() => { loadTransfers(); loadAccounts() }} accounts={accounts} />
      <ManualAdjustmentDialog open={adjustOpen} onOpenChange={setAdjustOpen} onSaved={loadAccounts} accounts={accounts} />
    </div>
  )
}
