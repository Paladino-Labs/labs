"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Pause, Play, X, Ticket } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import type { Promotion } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { PromotionBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { DateTimePicker } from "@/components/DateTimePicker"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { DISCOUNT_TYPE_LABELS, APPLICATION_MODE_LABELS } from "@/lib/constants"

function discountValueDisplay(p: Promotion): string {
  if (p.discount_type === "PERCENTAGE") return p.discount_value != null ? `${p.discount_value}%` : "—"
  if (p.discount_type === "FIXED_AMOUNT") return formatBRLFromDecimal(p.discount_value)
  return "—"
}

function vigencia(p: Promotion): string {
  if (!p.valid_from && !p.valid_until) return "Sem prazo"
  const from = p.valid_from ? formatDateTime(p.valid_from) : "—"
  const until = p.valid_until ? formatDateTime(p.valid_until) : "—"
  return `${from} → ${until}`
}

/* ------------------------------- Criar promoção ------------------------------- */
function CreatePromotionDialog({ open, onOpenChange, onCreated }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onCreated: () => void
}) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [discountType, setDiscountType] = useState("PERCENTAGE")
  const [discountValue, setDiscountValue] = useState("")
  const [appMode, setAppMode] = useState("AUTOMATIC")
  const [priority, setPriority] = useState("0")
  const [validFrom, setValidFrom] = useState("")
  const [validUntil, setValidUntil] = useState("")
  const [maxUses, setMaxUses] = useState("")
  const [maxPerCustomer, setMaxPerCustomer] = useState("")
  const [cumulative, setCumulative] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setName(""); setDescription(""); setDiscountType("PERCENTAGE"); setDiscountValue("")
      setAppMode("AUTOMATIC"); setPriority("0"); setValidFrom(""); setValidUntil("")
      setMaxUses(""); setMaxPerCustomer(""); setCumulative(false)
    }
  }, [open])

  const needsValue = discountType === "PERCENTAGE" || discountType === "FIXED_AMOUNT" || discountType === "OVERRIDE_PRICE"

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.post("/promotions", {
        name: name.trim(),
        description: description || null,
        discount_type: discountType,
        discount_value: needsValue && discountValue ? parseFloat(discountValue) : null,
        application_mode: appMode,
        cumulative,
        priority: Number(priority) || 0,
        valid_from: validFrom ? new Date(validFrom).toISOString() : null,
        valid_until: validUntil ? new Date(validUntil).toISOString() : null,
        max_uses: maxUses ? parseInt(maxUses, 10) : null,
        max_uses_per_customer: maxPerCustomer ? parseInt(maxPerCustomer, 10) : null,
      })
      toast.success("Promoção criada")
      onOpenChange(false)
      onCreated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar promoção")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>Nova promoção</DialogTitle></DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="pr-name">Nome *</Label>
            <Input id="pr-name" value={name} onChange={(e) => setName(e.target.value)} required maxLength={255} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="pr-desc">Descrição</Label>
            <Textarea id="pr-desc" value={description} onChange={(e) => setDescription(e.target.value)} rows={2} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label>Tipo de desconto</Label>
              <Select value={discountType} onValueChange={(v) => v && setDiscountType(v)}>
                <SelectTrigger className="w-full"><SelectValue>{DISCOUNT_TYPE_LABELS[discountType]}</SelectValue></SelectTrigger>
                <SelectContent>
                  {Object.keys(DISCOUNT_TYPE_LABELS).map((t) => (
                    <SelectItem key={t} value={t}>{DISCOUNT_TYPE_LABELS[t]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="pr-value">Valor</Label>
              <Input id="pr-value" type="number" min="0" step="0.01" value={discountValue}
                onChange={(e) => setDiscountValue(e.target.value)}
                disabled={!needsValue}
                placeholder={discountType === "PERCENTAGE" ? "0–100" : needsValue ? "0.00" : "—"} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label>Aplicação</Label>
              <Select value={appMode} onValueChange={(v) => v && setAppMode(v)}>
                <SelectTrigger className="w-full"><SelectValue>{APPLICATION_MODE_LABELS[appMode]}</SelectValue></SelectTrigger>
                <SelectContent>
                  {Object.keys(APPLICATION_MODE_LABELS).map((m) => (
                    <SelectItem key={m} value={m}>{APPLICATION_MODE_LABELS[m]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="pr-priority">Prioridade</Label>
              <Input id="pr-priority" type="number" value={priority} onChange={(e) => setPriority(e.target.value)} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pr-from">Início</Label>
              <DateTimePicker id="pr-from" value={validFrom} onChange={setValidFrom} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="pr-until">Fim</Label>
              <DateTimePicker id="pr-until" value={validUntil} onChange={setValidUntil} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="pr-max">Máx. usos</Label>
              <Input id="pr-max" type="number" min="1" value={maxUses} onChange={(e) => setMaxUses(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="pr-maxc">Máx. por cliente</Label>
              <Input id="pr-maxc" type="number" min="1" value={maxPerCustomer} onChange={(e) => setMaxPerCustomer(e.target.value)} />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <Label htmlFor="pr-cumulative">Cumulativa</Label>
            <Switch id="pr-cumulative" checked={cumulative} onCheckedChange={setCumulative} />
          </div>
          <p className="text-xs text-muted-foreground">
            Condições avançadas em breve — edição via API por enquanto.
          </p>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !name.trim()}>{saving ? "Criando…" : "Criar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ----------------------------------- Página ----------------------------------- */
export default function PromotionsPage() {
  const [promotions, setPromotions] = useState<Promotion[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [cancelTarget, setCancelTarget] = useState<Promotion | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setPromotions(await api.get<Promotion[]>("/promotions"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function transition(p: Promotion, action: "activate" | "pause") {
    setBusy(p.id)
    try {
      await api.patch(`/promotions/${p.id}/${action}`, {})
      toast.success(action === "activate" ? "Promoção ativada" : "Promoção pausada")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro na operação")
    } finally {
      setBusy(null)
    }
  }

  async function handleCancel() {
    if (!cancelTarget) return
    setBusy(cancelTarget.id)
    try {
      await api.patch(`/promotions/${cancelTarget.id}/cancel`, {})
      toast.success("Promoção cancelada")
      setCancelTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao cancelar")
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Comercial" title="Promoções" description="Regras de desconto e cupons.">
        <Button onClick={() => setCreateOpen(true)}>+ Nova promoção</Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : promotions.length === 0 ? (
        <EmptyState title="Nenhuma promoção" description="Crie a primeira promoção." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Nome</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-left font-medium">Valor</th>
                <th className="px-4 py-3 text-left font-medium">Modo</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Vigência</th>
                <th className="px-4 py-3 text-left font-medium">Usos</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {promotions.map((p) => {
                const disabled = busy === p.id
                return (
                  <tr key={p.id} className="align-top transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 font-medium">{p.name}</td>
                    <td className="px-4 py-3">{DISCOUNT_TYPE_LABELS[p.discount_type] ?? p.discount_type}</td>
                    <td className="px-4 py-3">{discountValueDisplay(p)}</td>
                    <td className="px-4 py-3">{APPLICATION_MODE_LABELS[p.application_mode] ?? p.application_mode}</td>
                    <td className="px-4 py-3"><PromotionBadge status={p.status} /></td>
                    <td className="px-4 py-3 text-xs text-muted-foreground whitespace-nowrap">{vigencia(p)}</td>
                    <td className="px-4 py-3">{p.uses_count}{p.max_uses != null ? `/${p.max_uses}` : ""}</td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col items-end gap-1.5">
                        <div className="flex items-center gap-2">
                          {(p.status === "DRAFT" || p.status === "PAUSED") && (
                            <Button size="sm" variant="outline" disabled={disabled} onClick={() => transition(p, "activate")}>
                              <Play className="h-3.5 w-3.5" /> Ativar
                            </Button>
                          )}
                          {p.status === "ACTIVE" && (
                            <Button size="sm" variant="outline" disabled={disabled} onClick={() => transition(p, "pause")}>
                              <Pause className="h-3.5 w-3.5" /> Pausar
                            </Button>
                          )}
                          {(p.status === "DRAFT" || p.status === "ACTIVE" || p.status === "PAUSED") && (
                            <Button size="sm" variant="ghost" className="text-destructive" disabled={disabled} onClick={() => setCancelTarget(p)}>
                              <X className="h-3.5 w-3.5" /> Cancelar
                            </Button>
                          )}
                        </div>
                        <Button size="sm" variant="ghost" render={<Link href={`/promocoes/${p.id}/cupons`} />}>
                          <Ticket className="h-3.5 w-3.5" /> Cupons
                        </Button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <CreatePromotionDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={load} />

      <Dialog open={!!cancelTarget} onOpenChange={(v) => !v && setCancelTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar promoção</DialogTitle>
            <DialogDescription>
              Cancelar a promoção “{cancelTarget?.name}”? Promoções são imutáveis — não há como reativar uma promoção cancelada.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleCancel}>Cancelar promoção</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
