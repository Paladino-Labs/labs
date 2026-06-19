"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { IMPERSONATION_MODE_LABELS } from "@/lib/constants"
import { useImpersonation } from "@/context/ImpersonationContext"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

interface Tenant {
  id: string
  name: string
  slug: string
  status: string
  active: boolean
  created_at: string
}

interface Grant {
  grant_id: string
  company_id: string
  mode: string
  reason: string
  expires_at: string
  revoked_at: string | null
  created_at: string
}

const MODE_OPTIONS = ["READ_ONLY", "ELEVATED"] as const

export default function OwnerImpersonationPage() {
  const { startImpersonation } = useImpersonation()

  const [tenants, setTenants] = useState<Tenant[]>([])
  const [grants, setGrants] = useState<Grant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Form de criação
  const [companyId, setCompanyId] = useState("")
  const [mode, setMode] = useState<string>("READ_ONLY")
  const [duration, setDuration] = useState("30")
  const [reason, setReason] = useState("")
  const [formError, setFormError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  // Encerrar grant
  const [endTarget, setEndTarget] = useState<Grant | null>(null)
  const [ending, setEnding] = useState(false)

  const loadGrants = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await api.get<{ items: Grant[]; total: number }>("/platform/impersonation/grants")
      setGrants(res.items)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  const loadTenants = useCallback(async () => {
    try {
      const res = await api.get<{ items: Tenant[]; total: number }>("/platform/tenants")
      setTenants(res.items)
    } catch {
      // lista de tenants é auxiliar; falha não bloqueia a tela
    }
  }, [])

  useEffect(() => { loadGrants() }, [loadGrants])
  useEffect(() => { loadTenants() }, [loadTenants])

  function tenantName(cid: string): string {
    return tenants.find((t) => t.id === cid)?.name ?? cid
  }

  // ELEVATED exige motivo ≥ 20 chars (espelha o 422 do backend)
  const reasonTooShort = mode === "ELEVATED" && reason.trim().length < 20
  const durationNum = Number(duration)
  const durationInvalid = !Number.isInteger(durationNum) || durationNum < 1 || durationNum > 480
  const canCreate = !!companyId && !!reason.trim() && !reasonTooShort && !durationInvalid

  async function handleCreate() {
    setFormError(null)
    if (!canCreate) return
    setCreating(true)
    try {
      const res = await api.post<{ grant_id: string; expires_at: string; mode: string }>(
        "/platform/impersonation/grants",
        { company_id: companyId, mode, reason: reason.trim(), duration_minutes: durationNum },
      )
      toast.success("Acesso criado")
      startImpersonation({
        grant_id: res.grant_id,
        company_id: companyId,
        company_name: tenantName(companyId),
        mode: res.mode ?? mode,
        expires_at: res.expires_at,
      })
      // limpa form e recarrega lista
      setReason("")
      setCompanyId("")
      setMode("READ_ONLY")
      setDuration("30")
      loadGrants()
    } catch (err: unknown) {
      setFormError((err as Error).message ?? "Erro ao criar acesso")
    } finally {
      setCreating(false)
    }
  }

  async function handleEnd() {
    if (!endTarget) return
    setEnding(true)
    try {
      await api.delete(`/platform/impersonation/grants/${endTarget.grant_id}`)
      toast.success("Acesso encerrado")
      setEndTarget(null)
      loadGrants()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao encerrar acesso")
    } finally {
      setEnding(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Impersonation"
        description="Crie acessos temporários a tenants para investigação."
      />

      {/* Criar acesso */}
      <Card>
        <CardHeader><CardTitle>Criar acesso</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label>Tenant</Label>
              <Select value={companyId} onValueChange={(v) => v && setCompanyId(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Selecione…">
                    {companyId ? tenantName(companyId) : "Selecione…"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {tenants.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Modo</Label>
              <Select value={mode} onValueChange={(v) => v && setMode(v)}>
                <SelectTrigger className="w-full">
                  <SelectValue>{IMPERSONATION_MODE_LABELS[mode] ?? mode}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {MODE_OPTIONS.map((m) => (
                    <SelectItem key={m} value={m}>{IMPERSONATION_MODE_LABELS[m]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="imp-duration">Duração (minutos)</Label>
            <Input
              id="imp-duration"
              type="number"
              min={1}
              max={480}
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              className="w-full"
            />
            {durationInvalid && (
              <p className="text-xs text-destructive">A duração deve estar entre 1 e 480 minutos.</p>
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="imp-reason">Motivo</Label>
            <Textarea
              id="imp-reason"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={3}
              placeholder="Descreva o motivo do acesso…"
            />
            {reasonTooShort && (
              <p className="text-xs text-destructive">
                O modo Elevado exige um motivo com pelo menos 20 caracteres.
              </p>
            )}
          </div>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="flex justify-end">
            <Button onClick={handleCreate} disabled={!canCreate || creating}>
              {creating ? "Criando…" : "Criar acesso"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Grants ativos */}
      <section className="space-y-3">
        <h2 className="font-display text-xl tracking-wide text-foreground">Grants ativos</h2>
        {loading ? (
          <Skeleton className="h-48 w-full" />
        ) : error ? (
          <ErrorState message={error} onRetry={loadGrants} />
        ) : grants.length === 0 ? (
          <EmptyState title="Nenhum acesso ativo" description="Crie um acesso acima para iniciar uma sessão." />
        ) : (
          <div className="rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Modo</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Expira em</TableHead>
                  <TableHead>Criado em</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {grants.map((g) => (
                  <TableRow key={g.grant_id}>
                    <TableCell className="font-medium">{tenantName(g.company_id)}</TableCell>
                    <TableCell>
                      <Badge variant={g.mode === "ELEVATED" ? "destructive" : "secondary"}>
                        {IMPERSONATION_MODE_LABELS[g.mode] ?? g.mode}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-md whitespace-normal text-muted-foreground">{g.reason || "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(g.expires_at)}</TableCell>
                    <TableCell className="text-muted-foreground">{formatDateTime(g.created_at)}</TableCell>
                    <TableCell className="text-right">
                      <Button size="sm" variant="ghost" className="text-destructive" onClick={() => setEndTarget(g)}>
                        Encerrar
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </section>

      {/* Encerrar grant */}
      <Dialog open={!!endTarget} onOpenChange={(v) => { if (!v) setEndTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Encerrar acesso</DialogTitle>
            <DialogDescription>
              O grant será revogado e não poderá mais ser usado. Esta ação é registrada em auditoria.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleEnd} disabled={ending}>
              {ending ? "Encerrando…" : "Encerrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
