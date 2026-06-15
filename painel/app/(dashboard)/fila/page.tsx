"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Bell, Trash2 } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { Customer } from "@/types"
import { timeAgo } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

interface WaitlistEntry {
  id: string
  customer_id: string
  scope_type: "SERVICE" | "PROFESSIONAL" | "PRODUCT"
  service_id?: string | null
  professional_id?: string | null
  product_id?: string | null
  status: string
  priority: number
  source_channel?: string | null
  notified_at?: string | null
  created_at?: string | null
}

interface WaitlistConfig {
  enabled: boolean
  priority_mode: string
  notification_window_hours: number
}

const SCOPE_LABEL: Record<string, string> = {
  SERVICE: "Serviço",
  PROFESSIONAL: "Profissional",
  PRODUCT: "Produto",
}

const ENTRY_STATUS: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  WAITING:  { label: "Aguardando", variant: "secondary" },
  NOTIFIED: { label: "Notificado", variant: "default" },
  EXPIRED:  { label: "Expirado",   variant: "outline" },
  FULFILLED:{ label: "Atendido",   variant: "outline" },
  CANCELLED:{ label: "Cancelado",  variant: "outline" },
}

export default function FilaPage() {
  const { role } = useAuth()
  const canConfig = role === "OWNER" || role === "ADMIN"

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operação"
        title="Fila de espera"
        description="Clientes aguardando vaga por serviço, profissional ou produto."
      />
      <Tabs defaultValue="entries">
        <TabsList>
          <TabsTrigger value="entries">Entradas</TabsTrigger>
          {canConfig && <TabsTrigger value="config">Configuração</TabsTrigger>}
        </TabsList>
        <TabsContent value="entries"><EntriesTab /></TabsContent>
        {canConfig && <TabsContent value="config"><ConfigTab /></TabsContent>}
      </Tabs>
    </div>
  )
}

function EntriesTab() {
  const [entries, setEntries] = useState<WaitlistEntry[]>([])
  const [names, setNames] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState("all")
  const [scopeFilter, setScopeFilter] = useState("all")

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (scopeFilter !== "all") params.set("scope_type", scopeFilter)
    const qs = params.toString()
    try {
      const data = await api.get<WaitlistEntry[]>(`/waitlist/entries${qs ? `?${qs}` : ""}`)
      setEntries(data)
      try {
        const customers = await api.get<Customer[]>("/customers/")
        setNames(new Map(customers.map((c) => [c.id, c.name])))
      } catch { /* nomes ficam como ID */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, scopeFilter])

  useEffect(() => { load() }, [load])

  async function handleRemove(id: string) {
    try {
      await api.delete(`/waitlist/entries/${id}`)
      toast.success("Removido da fila")
      setEntries((prev) => prev.filter((e) => e.id !== id))
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao remover")
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-44">
              <SelectValue>{statusFilter === "all" ? "Todos" : ENTRY_STATUS[statusFilter]?.label ?? statusFilter}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="WAITING">Aguardando</SelectItem>
              <SelectItem value="NOTIFIED">Notificado</SelectItem>
              <SelectItem value="EXPIRED">Expirado</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label>Escopo</Label>
          <Select value={scopeFilter} onValueChange={(v) => v && setScopeFilter(v)}>
            <SelectTrigger className="w-44">
              <SelectValue>{scopeFilter === "all" ? "Todos" : SCOPE_LABEL[scopeFilter] ?? scopeFilter}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos</SelectItem>
              <SelectItem value="SERVICE">Serviço</SelectItem>
              <SelectItem value="PROFESSIONAL">Profissional</SelectItem>
              <SelectItem value="PRODUCT">Produto</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Tooltip>
          <TooltipTrigger render={<span className="inline-flex" />}>
            <Button variant="outline" disabled>
              <Bell size={16} strokeWidth={1.5} /> Notificar manualmente
            </Button>
          </TooltipTrigger>
          <TooltipContent>Em breve</TooltipContent>
        </Tooltip>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : entries.length === 0 ? (
        <EmptyState title="Fila vazia" description="Nenhum cliente aguardando no momento." />
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Cliente</TableHead>
                <TableHead>Escopo</TableHead>
                <TableHead className="text-right">Prioridade</TableHead>
                <TableHead>Na fila</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((e) => {
                const badge = ENTRY_STATUS[e.status] ?? { label: e.status, variant: "outline" as const }
                return (
                  <TableRow key={e.id}>
                    <TableCell>{names.get(e.customer_id) ?? e.customer_id}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{SCOPE_LABEL[e.scope_type] ?? e.scope_type}</Badge>
                    </TableCell>
                    <TableCell className="text-right font-mono">{e.priority}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{timeAgo(e.created_at)}</TableCell>
                    <TableCell><Badge variant={badge.variant}>{badge.label}</Badge></TableCell>
                    <TableCell>
                      <Dialog>
                        <DialogTrigger render={<Button size="icon-sm" variant="ghost" />}>
                          <Trash2 size={16} strokeWidth={1.5} />
                        </DialogTrigger>
                        <DialogContent>
                          <DialogHeader>
                            <DialogTitle>Remover da fila</DialogTitle>
                            <DialogDescription>
                              Remover {names.get(e.customer_id) ?? "este cliente"} da fila de espera?
                            </DialogDescription>
                          </DialogHeader>
                          <DialogFooter>
                            <DialogClose render={<Button variant="outline" />}>Cancelar</DialogClose>
                            <DialogClose render={<Button variant="destructive" />} onClick={() => handleRemove(e.id)}>
                              Remover
                            </DialogClose>
                          </DialogFooter>
                        </DialogContent>
                      </Dialog>
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function ConfigTab() {
  const [config, setConfig] = useState<WaitlistConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setConfig(await api.get<WaitlistConfig>("/waitlist/config"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleSave() {
    if (!config) return
    setSaving(true)
    try {
      await api.put("/waitlist/config", config)
      toast.success("Configuração salva")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  if (loading) return <Skeleton className="h-64 w-full" />
  if (error || !config) return <ErrorState message={error ?? undefined} onRetry={load} />

  return (
    <Card className="max-w-lg">
      <CardHeader><CardTitle>Configuração da fila</CardTitle></CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between">
          <div>
            <Label>Fila habilitada</Label>
            <p className="text-xs text-muted-foreground">Permite que clientes entrem na lista de espera.</p>
          </div>
          <Switch
            checked={config.enabled}
            onCheckedChange={(v) => setConfig({ ...config, enabled: v })}
          />
        </div>

        <div className="space-y-1">
          <Label>Modo de prioridade</Label>
          <Select
            value={config.priority_mode}
            onValueChange={(v) => v && setConfig({ ...config, priority_mode: v })}
          >
            <SelectTrigger className="w-full">
              <SelectValue>{config.priority_mode === "FIFO" ? "Ordem de chegada (FIFO)" : "Por prioridade"}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="FIFO">Ordem de chegada (FIFO)</SelectItem>
              <SelectItem value="PRIORITY">Por prioridade</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="window">Janela de notificação (horas)</Label>
          <Input
            id="window"
            type="number"
            min={1}
            value={config.notification_window_hours}
            onChange={(e) => setConfig({ ...config, notification_window_hours: Number(e.target.value) })}
            className="w-40"
          />
        </div>

        <Button onClick={handleSave} disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
      </CardContent>
    </Card>
  )
}
