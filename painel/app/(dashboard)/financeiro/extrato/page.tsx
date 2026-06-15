"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
import { toast } from "sonner"
import { CheckCircle2, Loader2, Upload, XCircle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { cn } from "@/lib/utils"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { StatementEntry, StatementBatch, FinancialAccount, FinancialMovement } from "@/types"
import { STATEMENT_STATUS_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { StatementBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface ImportResponse {
  imported: number; skipped_duplicates: number; skipped_invalid: number; auto_matched: number; batch_id: string
}

const STATUS_FILTER: Record<string, string> = {
  all: "Todos", PENDING: "Pendente", MATCHED: "Conciliado", DISMISSED: "Dispensado",
}

/* --------------------------------- Import --------------------------------- */
function ImportDialog({ open, onOpenChange, onImported, accounts }: {
  open: boolean; onOpenChange: (v: boolean) => void; onImported: () => void; accounts: FinancialAccount[]
}) {
  const [accountId, setAccountId] = useState("")
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string[]>([])
  const [colDate, setColDate] = useState("data")
  const [colAmount, setColAmount] = useState("valor")
  const [colDesc, setColDesc] = useState("descricao")
  const [colDir, setColDir] = useState("")
  const [uploading, setUploading] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (open) {
      setAccountId(""); setFile(null); setPreview([])
      setColDate("data"); setColAmount("valor"); setColDesc("descricao"); setColDir("")
    }
  }, [open])

  function handleFile(f: File | null) {
    setFile(f)
    setPreview([])
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      const text = String(reader.result ?? "")
      setPreview(text.split(/\r?\n/).filter(Boolean).slice(0, 5))
    }
    reader.readAsText(f)
  }

  async function handleImport() {
    if (!file || !accountId || !colDate || !colAmount) return
    setUploading(true)
    try {
      const mapping: Record<string, string> = { date: colDate, amount: colAmount }
      if (colDesc) mapping.description = colDesc
      if (colDir) mapping.direction = colDir
      const fd = new FormData()
      fd.append("file", file)
      fd.append("account_id", accountId)
      fd.append("column_mapping", JSON.stringify(mapping))
      const res = await api.postForm<ImportResponse>("/financial/statement/import", fd)
      toast.success(`${res.imported} importadas · ${res.skipped_duplicates} duplicadas · ${res.auto_matched} auto-conciliadas`)
      onOpenChange(false)
      onImported()
    } catch (err: unknown) {
      const e = err as { status?: number; message?: string }
      if (e.status === 403) toast.error("Ação não habilitada para este tenant")
      else toast.error(e.message ?? "Erro ao importar extrato")
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Importar extrato CSV</DialogTitle>
          <DialogDescription>Multipart: file + account_id + column_mapping (JSON).</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1 max-h-[65vh] overflow-y-auto pr-1">
          <div className="space-y-1">
            <Label>Conta</Label>
            <Select value={accountId || "none"} onValueChange={(v) => v && setAccountId(v === "none" ? "" : v)}>
              <SelectTrigger className="w-full"><SelectValue>{accountId ? (accounts.find((a) => a.account_id === accountId)?.name ?? "—") : "Selecione"}</SelectValue></SelectTrigger>
              <SelectContent>{accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}</SelectContent>
            </Select>
          </div>

          <button type="button" onClick={() => fileInput.current?.click()}
            className="flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border bg-card/40 px-6 py-8 text-sm text-muted-foreground transition-colors hover:border-primary">
            <Upload className="h-5 w-5" />
            {file ? file.name : "Arraste o CSV ou clique para selecionar"}
          </button>
          <input ref={fileInput} type="file" accept=".csv" hidden
            onChange={(e) => handleFile(e.target.files?.[0] ?? null)} />

          {preview.length > 0 && (
            <div className="rounded-lg border border-border bg-muted/30 p-2 text-xs font-mono">
              {preview.map((line, i) => (
                <div key={i} className={cn("truncate", i === 0 && "font-semibold text-foreground")}>{line}</div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label htmlFor="col-date">Coluna data *</Label>
              <Input id="col-date" value={colDate} onChange={(e) => setColDate(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="col-amount">Coluna valor *</Label>
              <Input id="col-amount" value={colAmount} onChange={(e) => setColAmount(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="col-desc">Coluna descrição</Label>
              <Input id="col-desc" value={colDesc} onChange={(e) => setColDesc(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="col-dir">Coluna direção</Label>
              <Input id="col-dir" value={colDir} onChange={(e) => setColDir(e.target.value)} />
            </div>
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleImport} disabled={uploading || !file || !accountId || !colDate || !colAmount}>
            {uploading && <Loader2 className="h-4 w-4 animate-spin" />}
            {uploading ? "Importando…" : "Importar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* --------------------------------- Match --------------------------------- */
function MatchDialog({ entry, onClose, onMatched }: {
  entry: StatementEntry | null; onClose: () => void; onMatched: () => void
}) {
  const [suggestions, setSuggestions] = useState<FinancialMovement[]>([])
  const [loading, setLoading] = useState(false)
  const [selected, setSelected] = useState("")
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (!entry) return
    setSelected(""); setLoading(true)
    api.get<FinancialMovement[]>(`/financial/statement/${entry.id}/suggestions`)
      .then(setSuggestions)
      .catch((err: Error) => toast.error(err.message ?? "Erro ao carregar sugestões"))
      .finally(() => setLoading(false))
  }, [entry])

  async function handleMatch() {
    if (!entry || !selected) return
    setBusy(true)
    try {
      await api.post(`/financial/statement/${entry.id}/match`, { movement_id: selected })
      toast.success("Lançamento conciliado")
      onClose(); onMatched()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao conciliar")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={!!entry} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Sugestões de match</DialogTitle>
          <DialogDescription>{entry?.description} — {entry && formatBRLFromDecimal(entry.amount)}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2 py-1 max-h-[50vh] overflow-y-auto">
          {loading ? (
            <Skeleton className="h-32 w-full" />
          ) : suggestions.length === 0 ? (
            <EmptyState message="Nenhuma sugestão encontrada." />
          ) : suggestions.map((m) => (
            <button key={m.movement_id} type="button" onClick={() => setSelected(m.movement_id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition-colors",
                selected === m.movement_id ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40",
              )}>
              <span className={cn("h-4 w-4 shrink-0 rounded-full border", selected === m.movement_id ? "border-primary bg-primary" : "border-muted-foreground")} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">
                  {m.type === "INFLOW" ? "Entrada" : "Saída"} · {formatBRLFromDecimal(m.amount)}
                </span>
                <span className="block text-xs text-muted-foreground">{formatDateTime(m.occurred_at)} · {m.source_type}</span>
              </span>
            </button>
          ))}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleMatch} disabled={busy || !selected}>Confirmar match</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* --------------------------------- Página --------------------------------- */
export default function ExtratoPage() {
  const { role } = useAuth()
  const canWrite = role === "OWNER" || role === "ADMIN" || role === "OPERATOR"

  const [entries, setEntries] = useState<StatementEntry[]>([])
  const [batches, setBatches] = useState<StatementBatch[]>([])
  const [accounts, setAccounts] = useState<FinancialAccount[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [importOpen, setImportOpen] = useState(false)
  const [matchEntry, setMatchEntry] = useState<StatementEntry | null>(null)
  const [dismissEntry, setDismissEntry] = useState<StatementEntry | null>(null)
  const [dismissReason, setDismissReason] = useState("")
  const [busy, setBusy] = useState(false)

  const [statusFilter, setStatusFilter] = useState("all")
  const [batchFilter, setBatchFilter] = useState("all")
  const [accountFilter, setAccountFilter] = useState("all")

  const accountMap = useMemo(() => new Map(accounts.map((a) => [a.account_id, a.name])), [accounts])

  useEffect(() => {
    api.get<FinancialAccount[]>("/financial/accounts").then(setAccounts).catch(() => {})
    api.get<StatementBatch[]>("/financial/statement/batches").then(setBatches).catch(() => {})
  }, [])

  const reloadBatches = useCallback(() => {
    api.get<StatementBatch[]>("/financial/statement/batches").then(setBatches).catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (batchFilter !== "all") params.set("batch_id", batchFilter)
    if (accountFilter !== "all") params.set("account_id", accountFilter)
    const q = params.toString()
    try {
      setEntries(await api.get<StatementEntry[]>(`/financial/statement/${q ? `?${q}` : ""}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, batchFilter, accountFilter])

  useEffect(() => { load() }, [load])

  async function handleDismiss() {
    if (!dismissEntry || !dismissReason.trim()) return
    setBusy(true)
    try {
      await api.post(`/financial/statement/${dismissEntry.id}/dismiss`, { reason: dismissReason.trim() })
      toast.success("Lançamento dispensado")
      setDismissEntry(null); setDismissReason("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao dispensar")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Financeiro" title="Extrato bancário" description="Importação CSV, match e dispensa de lançamentos.">
        {canWrite && (
          <Button onClick={() => setImportOpen(true)}><Upload className="h-4 w-4" /> Importar CSV</Button>
        )}
      </PageHeader>

      {/* Lotes */}
      {batches.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {batches.map((b) => (
            <Card key={b.batch_id}>
              <CardContent className="p-5">
                <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{accountMap.get(b.account_id) ?? "—"}</p>
                <p className="mt-1 font-display text-xl tracking-wide">{b.batch_id.slice(0, 8)}</p>
                {b.imported_at && <p className="text-xs text-muted-foreground">{formatDateTime(b.imported_at)}</p>}
                <div className="mt-3 grid grid-cols-4 gap-2 text-center">
                  <div><p className="font-display text-lg">{b.total}</p><p className="text-[10px] text-muted-foreground">Total</p></div>
                  <div><p className="font-display text-lg text-success">{b.matched}</p><p className="text-[10px] text-muted-foreground">Conciliado</p></div>
                  <div><p className="font-display text-lg text-amber-600 dark:text-amber-400">{b.pending}</p><p className="text-[10px] text-muted-foreground">Pendente</p></div>
                  <div><p className="font-display text-lg text-muted-foreground">{b.dismissed}</p><p className="text-[10px] text-muted-foreground">Dispensado</p></div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-full"><SelectValue>{STATUS_FILTER[statusFilter]}</SelectValue></SelectTrigger>
            <SelectContent>{Object.entries(STATUS_FILTER).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Lote</Label>
          <Select value={batchFilter} onValueChange={(v) => v && setBatchFilter(v)}>
            <SelectTrigger className="w-full"><SelectValue>{batchFilter === "all" ? "Todos" : batchFilter.slice(0, 8)}</SelectValue></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              {batches.map((b) => <SelectItem key={b.batch_id} value={b.batch_id}>{b.batch_id.slice(0, 8)}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Conta</Label>
          <Select value={accountFilter} onValueChange={(v) => v && setAccountFilter(v)}>
            <SelectTrigger className="w-full"><SelectValue>{accountFilter === "all" ? "Todas" : (accountMap.get(accountFilter) ?? "—")}</SelectValue></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              {accounts.map((a) => <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : entries.length === 0 ? (
        <EmptyState title="Nenhum lançamento" description="Importe um extrato CSV para começar." />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Data</th>
                <th className="px-4 py-3 text-left font-medium">Descrição</th>
                <th className="px-4 py-3 text-right font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Direção</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                {canWrite && <th className="px-4 py-3 text-right font-medium">Ações</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {entries.map((e) => (
                <tr key={e.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 text-xs text-muted-foreground">{formatDateTime(e.occurred_at)}</td>
                  <td className="px-4 py-3 font-medium">{e.description ?? "—"}</td>
                  <td className="px-4 py-3 text-right">{formatBRLFromDecimal(e.amount)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{e.direction === "INFLOW" ? "Entrada" : "Saída"}</td>
                  <td className="px-4 py-3"><StatementBadge status={e.status} /></td>
                  {canWrite && (
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        {e.status === "PENDING" && (
                          <>
                            <Button size="sm" variant="ghost" onClick={() => setMatchEntry(e)}>
                              <CheckCircle2 className="h-3.5 w-3.5" /> Ver sugestões
                            </Button>
                            <Button size="sm" variant="ghost" className="text-destructive"
                              onClick={() => { setDismissEntry(e); setDismissReason("") }}>
                              <XCircle className="h-3.5 w-3.5" /> Dispensar
                            </Button>
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {canWrite && (
        <ImportDialog open={importOpen} onOpenChange={setImportOpen}
          onImported={() => { load(); reloadBatches() }} accounts={accounts} />
      )}
      <MatchDialog entry={matchEntry} onClose={() => setMatchEntry(null)} onMatched={() => { load(); reloadBatches() }} />

      <Dialog open={!!dismissEntry} onOpenChange={(v) => !v && setDismissEntry(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Dispensar lançamento</DialogTitle>
            <DialogDescription>Informe o motivo da dispensa de “{dismissEntry?.description}”.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1 py-1">
            <Label htmlFor="dismiss-reason">Motivo *</Label>
            <Textarea id="dismiss-reason" value={dismissReason} onChange={(e) => setDismissReason(e.target.value)} rows={3} required />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDismiss} disabled={!dismissReason.trim() || busy}>Dispensar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
