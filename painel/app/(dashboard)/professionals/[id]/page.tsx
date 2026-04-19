"use client"

import { useEffect, useState, useCallback } from "react"
import { useRouter, useParams } from "next/navigation"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type {
  Professional,
  Service,
  WorkingHour,
  ScheduleBlock,
  ProfessionalService,
} from "@/types"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

// ── Horários ─────────────────────────────────────────────────────────────────
const WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

interface WhRow {
  weekday: number
  is_active: boolean
  opening_time: string   // "HH:MM"
  closing_time: string   // "HH:MM"
  saving: boolean
}

function defaultWh(weekday: number): WhRow {
  return {
    weekday,
    is_active: false,
    opening_time: "09:00",
    closing_time: "18:00",
    saving: false,
  }
}

function mergeWh(fetched: WorkingHour[]): WhRow[] {
  return Array.from({ length: 7 }, (_, i) => {
    const h = fetched.find((x) => x.weekday === i)
    if (h) {
      return {
        weekday: i,
        is_active: h.is_active,
        opening_time: h.opening_time.slice(0, 5),
        closing_time: h.closing_time.slice(0, 5),
        saving: false,
      }
    }
    return defaultWh(i)
  })
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function ProfessionalEditorPage() {
  const router = useRouter()
  const params = useParams()
  const profId = params.id as string

  // ── Estado ────────────────────────────────────────────────────────────────
  const [prof, setProf] = useState<Professional | null>(null)
  const [editName, setEditName] = useState("")
  const [savingInfo, setSavingInfo] = useState(false)

  const [whRows, setWhRows] = useState<WhRow[]>(
    Array.from({ length: 7 }, (_, i) => defaultWh(i))
  )

  const [profServices, setProfServices] = useState<ProfessionalService[]>([])
  const [allServices, setAllServices] = useState<Service[]>([])
  const [addServiceId, setAddServiceId] = useState("")
  const [addCommission, setAddCommission] = useState("")
  const [addingService, setAddingService] = useState(false)

  const [blocks, setBlocks] = useState<ScheduleBlock[]>([])
  const [blockOpen, setBlockOpen] = useState(false)
  const [blockForm, setBlockForm] = useState({ start_at: "", end_at: "", reason: "" })
  const [savingBlock, setSavingBlock] = useState(false)

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  // ── Carregamento inicial ───────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    try {
      setLoading(true)
      const [profData, wh, ps, svc, bl] = await Promise.all([
        api.get<Professional>(`/professionals/${profId}`),
        api.get<WorkingHour[]>(`/schedule/working-hours/${profId}`),
        api.get<ProfessionalService[]>(`/professionals/${profId}/services`),
        api.get<Service[]>("/services/"),
        api.get<ScheduleBlock[]>(`/schedule/blocks/${profId}`),
      ])
      setProf(profData)
      setEditName(profData.name)
      setWhRows(mergeWh(wh))
      setProfServices(ps)
      setAllServices(svc)
      setBlocks(bl)
    } catch (e: unknown) {
      setLoadError((e as Error).message ?? "Erro ao carregar profissional")
    } finally {
      setLoading(false)
    }
  }, [profId])

  useEffect(() => { fetchAll() }, [fetchAll])

  // ── Seção 1: Informações básicas ───────────────────────────────────────────
  async function handleSaveInfo() {
    setSavingInfo(true)
    try {
      await api.patch(`/professionals/${profId}`, { name: editName })
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setSavingInfo(false)
    }
  }

  async function handleToggleActive() {
    if (!prof) return
    try {
      await api.patch(`/professionals/${profId}`, { active: !prof.active })
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  // ── Seção 2: Horários ──────────────────────────────────────────────────────
  function patchWh(weekday: number, patch: Partial<WhRow>) {
    setWhRows((prev) =>
      prev.map((r) => (r.weekday === weekday ? { ...r, ...patch } : r))
    )
  }

  async function handleSaveWh(weekday: number) {
    const row = whRows[weekday]
    patchWh(weekday, { saving: true })
    try {
      await api.post("/schedule/working-hours", {
        professional_id: profId,
        weekday,
        opening_time: row.opening_time,
        closing_time: row.closing_time,
        is_active: row.is_active,
      })
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      patchWh(weekday, { saving: false })
    }
  }

  // ── Seção 3: Serviços ──────────────────────────────────────────────────────
  const availableToAdd = allServices.filter(
    (s) => s.active && !profServices.find((ps) => ps.service_id === s.id)
  )

  const addServiceLabel = addServiceId
    ? (allServices.find((s) => s.id === addServiceId)?.name ?? "")
    : ""

  async function handleAddService() {
    if (!addServiceId) return
    setAddingService(true)
    try {
      await api.post(`/professionals/${profId}/services`, {
        service_id: addServiceId,
        ...(addCommission ? { commission_percentage: parseFloat(addCommission) } : {}),
      })
      setAddServiceId("")
      setAddCommission("")
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setAddingService(false)
    }
  }

  async function handleRemoveService(serviceId: string) {
    if (!confirm("Remover este serviço do profissional?")) return
    try {
      await api.delete(`/professionals/${profId}/services/${serviceId}`)
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  // ── Seção 4: Bloqueios ─────────────────────────────────────────────────────
  async function handleAddBlock() {
    if (!blockForm.start_at || !blockForm.end_at) return
    setSavingBlock(true)
    try {
      await api.post("/schedule/blocks", {
        professional_id: profId,
        start_at: new Date(blockForm.start_at).toISOString(),
        end_at:   new Date(blockForm.end_at).toISOString(),
        ...(blockForm.reason ? { reason: blockForm.reason } : {}),
      })
      setBlockOpen(false)
      setBlockForm({ start_at: "", end_at: "", reason: "" })
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setSavingBlock(false)
    }
  }

  async function handleDeleteBlock(blockId: string) {
    if (!confirm("Remover este bloqueio de agenda?")) return
    try {
      await api.delete(`/schedule/blocks/${blockId}`)
      await fetchAll()
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading)   return <p className="text-muted-foreground">Carregando…</p>
  if (loadError) return <p className="text-destructive">{loadError}</p>
  if (!prof)     return null

  return (
    <div className="max-w-3xl space-y-6">

      {/* Cabeçalho */}
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push("/professionals")}
        >
          ← Voltar
        </Button>
        <h1 className="text-2xl font-bold">{prof.name}</h1>
        <ActiveBadge active={prof.active} />
      </div>

      {/* ── 1. Informações ──────────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Informações</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <Label>Nome</Label>
            <div className="flex gap-2">
              <Input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className="max-w-xs"
              />
              <Button
                onClick={handleSaveInfo}
                disabled={savingInfo || editName.trim() === prof.name}
              >
                {savingInfo ? "Salvando…" : "Salvar nome"}
              </Button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Status atual:</span>
            <ActiveBadge active={prof.active} />
            <Button
              variant={prof.active ? "destructive" : "default"}
              size="sm"
              onClick={handleToggleActive}
            >
              {prof.active ? "Desativar" : "Ativar"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* ── 2. Horários de atendimento ───────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Horários de Atendimento</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-28">Dia</TableHead>
                <TableHead className="w-16">Ativo</TableHead>
                <TableHead>Abertura</TableHead>
                <TableHead>Fechamento</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {whRows.map((row) => (
                <TableRow key={row.weekday}>
                  <TableCell className="font-medium">
                    {WEEKDAYS[row.weekday]}
                  </TableCell>
                  <TableCell>
                    <input
                      type="checkbox"
                      checked={row.is_active}
                      onChange={(e) =>
                        patchWh(row.weekday, { is_active: e.target.checked })
                      }
                      className="h-4 w-4 accent-primary cursor-pointer"
                    />
                  </TableCell>
                  <TableCell>
                    <input
                      type="time"
                      value={row.opening_time}
                      disabled={!row.is_active}
                      onChange={(e) =>
                        patchWh(row.weekday, { opening_time: e.target.value })
                      }
                      className="border rounded-md px-2 py-1 text-sm disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary/30"
                    />
                  </TableCell>
                  <TableCell>
                    <input
                      type="time"
                      value={row.closing_time}
                      disabled={!row.is_active}
                      onChange={(e) =>
                        patchWh(row.weekday, { closing_time: e.target.value })
                      }
                      className="border rounded-md px-2 py-1 text-sm disabled:opacity-40 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary/30"
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={row.saving}
                      onClick={() => handleSaveWh(row.weekday)}
                    >
                      {row.saving ? "…" : "Salvar"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* ── 3. Serviços atendidos ────────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <CardTitle>Serviços Atendidos</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {profServices.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum serviço associado a este profissional.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Serviço</TableHead>
                  <TableHead className="text-right">Preço</TableHead>
                  <TableHead className="text-right">Duração</TableHead>
                  <TableHead className="text-right">Comissão</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {profServices.map((ps) => (
                  <TableRow key={ps.id}>
                    <TableCell className="font-medium">{ps.service_name}</TableCell>
                    <TableCell className="text-right">
                      R$ {Number(ps.price).toFixed(2)}
                    </TableCell>
                    <TableCell className="text-right">{ps.duration} min</TableCell>
                    <TableCell className="text-right">
                      {ps.commission_percentage
                        ? `${ps.commission_percentage}%`
                        : "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleRemoveService(ps.service_id)}
                      >
                        Remover
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {/* Adicionar serviço */}
          {availableToAdd.length > 0 && (
            <div className="flex flex-wrap gap-2 items-end pt-3 border-t">
              <div className="space-y-1 flex-1 min-w-40">
                <Label className="text-xs text-muted-foreground">
                  Adicionar serviço
                </Label>
                <Select
                  value={addServiceId}
                  onValueChange={(v) => v && setAddServiceId(v)}
                >
                  <SelectTrigger>
                    <span
                      className={
                        addServiceId ? "text-foreground" : "text-muted-foreground"
                      }
                    >
                      {addServiceId ? addServiceLabel : "Selecione um serviço"}
                    </span>
                  </SelectTrigger>
                  <SelectContent>
                    {availableToAdd.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.name} — R$ {Number(s.price).toFixed(2)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-1 w-28">
                <Label className="text-xs text-muted-foreground">
                  Comissão (%)
                </Label>
                <Input
                  type="number"
                  placeholder="Ex: 40"
                  min="0"
                  max="100"
                  value={addCommission}
                  onChange={(e) => setAddCommission(e.target.value)}
                />
              </div>

              <Button
                onClick={handleAddService}
                disabled={addingService || !addServiceId}
              >
                {addingService ? "…" : "Adicionar"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── 4. Bloqueios de agenda ───────────────────────────────────────── */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Bloqueios de Agenda</CardTitle>
            <Button size="sm" onClick={() => setBlockOpen(true)}>
              + Novo Bloqueio
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {blocks.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhum bloqueio cadastrado. Use bloqueios para registrar férias,
              reuniões ou outros impedimentos.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Início</TableHead>
                  <TableHead>Fim</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {blocks.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(b.start_at)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap">
                      {formatDateTime(b.end_at)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {b.reason ?? "—"}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="destructive"
                        onClick={() => handleDeleteBlock(b.id)}
                      >
                        Remover
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog: novo bloqueio */}
      <Dialog open={blockOpen} onOpenChange={setBlockOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Novo Bloqueio de Agenda</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1">
              <Label>Início *</Label>
              <Input
                type="datetime-local"
                value={blockForm.start_at}
                onChange={(e) =>
                  setBlockForm((f) => ({ ...f, start_at: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1">
              <Label>Fim *</Label>
              <Input
                type="datetime-local"
                value={blockForm.end_at}
                onChange={(e) =>
                  setBlockForm((f) => ({ ...f, end_at: e.target.value }))
                }
              />
            </div>
            <div className="space-y-1">
              <Label>Motivo (opcional)</Label>
              <Input
                placeholder="Ex: Férias, Reunião, Evento"
                value={blockForm.reason}
                onChange={(e) =>
                  setBlockForm((f) => ({ ...f, reason: e.target.value }))
                }
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setBlockOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleAddBlock}
              disabled={savingBlock || !blockForm.start_at || !blockForm.end_at}
            >
              {savingBlock ? "Salvando…" : "Criar Bloqueio"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

    </div>
  )
}
