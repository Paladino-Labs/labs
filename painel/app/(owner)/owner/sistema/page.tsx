"use client"

import { useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { PageHeader } from "@/components/PageHeader"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// RBAC-2 — replay financeiro bloqueado na UI (princípio documentado; sem backend)
const BLOCKED_MODULES = new Set(["PaymentsEngine", "CommissionEngine", "FinancialCore"])

interface DeadLetterRow {
  module: string
  event: string
  error: string
}

// Mock estático (sem endpoint — Estágio 1+). Estrutura visual conforme contrato.
const DEAD_LETTER: DeadLetterRow[] = [
  { module: "PaymentsEngine",    event: "asaas.charge.failed",      error: "Timeout 504 ao consultar Asaas" },
  { module: "CommunicationCore", event: "whatsapp.send.failed",     error: "Token inválido" },
  { module: "CommissionEngine",  event: "commission.recalc.failed", error: "Divisão por zero em regra customizada" },
  { module: "BookingService",    event: "appointment.confirm.failed", error: "Conflito de horário detectado" },
  { module: "FinancialCore",     event: "ledger.entry.failed",      error: "Saldo negativo bloqueado" },
]

export default function OwnerSistemaPage() {
  // Reenvio de comunicação (real)
  const [logId, setLogId] = useState("")
  const [reason, setReason] = useState("")
  const [sending, setSending] = useState(false)
  const [result, setResult] = useState<{ new_log_id: string; status: string } | null>(null)
  const [sendError, setSendError] = useState<string | null>(null)

  // Replay (mock) — Dialog de motivo
  const [replayTarget, setReplayTarget] = useState<DeadLetterRow | null>(null)
  const [replayReason, setReplayReason] = useState("")

  const uuidValid = UUID_RE.test(logId.trim())
  const canSend = uuidValid && !!reason.trim()

  async function handleRedispatch() {
    setSendError(null); setResult(null)
    if (!canSend) return
    setSending(true)
    try {
      const res = await api.post<{ new_log_id: string; status: string; original_log_id: string }>(
        `/platform/communications/${logId.trim()}/redispatch`,
        { reason: reason.trim() },
      )
      setResult({ new_log_id: res.new_log_id, status: res.status })
      toast.success("Comunicação reenviada")
    } catch (err: unknown) {
      setSendError((err as Error).message ?? "Erro ao reenviar")
    } finally {
      setSending(false)
    }
  }

  function openReplay(row: DeadLetterRow) {
    setReplayReason("")
    setReplayTarget(row)
  }

  function confirmReplay() {
    // Sem backend — apenas feedback de protótipo.
    toast.info("Replay indisponível — sem backend (Estágio 1+).")
    setReplayTarget(null)
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Sistema"
        description="Operações de baixo nível na plataforma."
      />

      {/* Reenviar comunicação (real) */}
      <Card>
        <CardHeader>
          <CardTitle>Reenviar comunicação</CardTitle>
          <p className="text-sm text-muted-foreground">
            Apenas logs com status FAILED são aceitos. Esta ação é registrada em auditoria.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="sys-logid">log_id (UUID)</Label>
              <Input
                id="sys-logid"
                value={logId}
                onChange={(e) => setLogId(e.target.value)}
                placeholder="00000000-0000-0000-0000-000000000000"
                className="font-mono"
              />
              {logId.trim() && !uuidValid && (
                <p className="text-xs text-destructive">Informe um UUID válido.</p>
              )}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="sys-reason">Motivo</Label>
              <Textarea
                id="sys-reason"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={3}
                placeholder="Descreva o motivo do reenvio…"
              />
            </div>
          </div>
          {sendError && <p className="text-sm text-destructive">{sendError}</p>}
          {result && (
            <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
              <p>Novo log: <span className="font-mono text-xs">{result.new_log_id}</span></p>
              <p className="text-muted-foreground">Status: {result.status}</p>
            </div>
          )}
          <div className="flex justify-end">
            <Button onClick={handleRedispatch} disabled={!canSend || sending}>
              {sending ? "Reenviando…" : "Reenviar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Dead-letter / workers (mock — sem backend) */}
      <section className="space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="font-display text-xl tracking-wide text-foreground">Dead-letter / workers</h2>
          <Badge variant="outline">Em breve · mock</Badge>
        </div>
        <div className="rounded-lg border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Módulo</TableHead>
                <TableHead>Evento</TableHead>
                <TableHead>Erro</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {DEAD_LETTER.map((row) => {
                const blocked = BLOCKED_MODULES.has(row.module)
                return (
                  <TableRow key={`${row.module}-${row.event}`}>
                    <TableCell><Badge variant="outline" className="font-mono">{row.module}</Badge></TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{row.event}</TableCell>
                    <TableCell className="text-muted-foreground">{row.error}</TableCell>
                    <TableCell className="text-right">
                      {blocked ? (
                        <Tooltip>
                          <TooltipTrigger render={<span />}>
                            <Button size="sm" variant="outline" disabled>Replay</Button>
                          </TooltipTrigger>
                          <TooltipContent>
                            Replay bloqueado para módulos financeiros (RBAC-2).
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <Button size="sm" variant="outline" onClick={() => openReplay(row)}>Replay</Button>
                      )}
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      </section>

      {/* Replay (mock) */}
      <Dialog open={!!replayTarget} onOpenChange={(v) => { if (!v) setReplayTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Replay de evento</DialogTitle>
            <DialogDescription>
              {replayTarget ? `${replayTarget.module} · ${replayTarget.event}` : ""} — funcionalidade sem backend (Estágio 1+).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-1">
            <Label htmlFor="replay-reason">Motivo</Label>
            <Textarea
              id="replay-reason"
              value={replayReason}
              onChange={(e) => setReplayReason(e.target.value)}
              rows={3}
              placeholder="Descreva o motivo do replay…"
            />
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button onClick={confirmReplay} disabled={!replayReason.trim()}>Replay</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
