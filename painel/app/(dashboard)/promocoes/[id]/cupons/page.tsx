"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, Copy } from "lucide-react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import type { Promotion, Coupon, Customer } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CouponBadge, PromotionBadge } from "@/components/FsmBadge"
import { CustomerAutocomplete } from "@/components/CustomerAutocomplete"
import { DateTimePicker } from "@/components/DateTimePicker"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import { GENERATION_TYPE_LABELS, COUPON_REOPEN_LABELS } from "@/lib/constants"

function GenerateCouponsDialog({ promotionId, open, onOpenChange, onGenerated }: {
  promotionId: string
  open: boolean
  onOpenChange: (v: boolean) => void
  onGenerated: () => void
}) {
  const [genType, setGenType] = useState("BULK")
  const [quantity, setQuantity] = useState("10")
  const [prefix, setPrefix] = useState("")
  const [code, setCode] = useState("")
  const [maxUses, setMaxUses] = useState("1")
  const [customerId, setCustomerId] = useState("")
  const [expiresAt, setExpiresAt] = useState("")
  const [reopen, setReopen] = useState("NEVER_REOPEN")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (open) {
      setGenType("BULK"); setQuantity("10"); setPrefix(""); setCode("")
      setMaxUses("1"); setCustomerId(""); setExpiresAt(""); setReopen("NEVER_REOPEN")
    }
  }, [open])

  // SINGLE_USE força max_uses = 1
  useEffect(() => {
    if (genType === "SINGLE_USE") setMaxUses("1")
  }, [genType])

  async function handleGenerate() {
    if (genType === "PER_CUSTOMER" && !customerId) {
      toast.error("Selecione um cliente.")
      return
    }
    setSaving(true)
    try {
      const body: Record<string, unknown> = {
        generation_type: genType,
        coupon_reopen_policy: reopen,
        ...(expiresAt ? { expires_at: new Date(expiresAt).toISOString() } : {}),
      }
      if (genType === "BULK") {
        body.quantity = parseInt(quantity, 10) || 1
        if (prefix) body.prefix = prefix
        if (maxUses) body.max_uses = parseInt(maxUses, 10)
      } else if (genType === "SINGLE_USE") {
        body.max_uses = 1
        if (code) body.code = code
        else if (prefix) body.prefix = prefix
      } else if (genType === "PER_CUSTOMER") {
        body.customer_id = customerId
        if (maxUses) body.max_uses = parseInt(maxUses, 10)
      }
      const created = await api.post<Coupon[]>(`/promotions/${promotionId}/coupons`, body)
      toast.success(`${Array.isArray(created) ? created.length : 0} cupom(ns) gerado(s)`)
      onOpenChange(false)
      onGenerated()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao gerar cupons")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>Gerar cupons</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label>Tipo de geração</Label>
            <Select value={genType} onValueChange={(v) => v && setGenType(v)}>
              <SelectTrigger className="w-full"><SelectValue>{GENERATION_TYPE_LABELS[genType]}</SelectValue></SelectTrigger>
              <SelectContent>
                {Object.keys(GENERATION_TYPE_LABELS).map((t) => (
                  <SelectItem key={t} value={t}>{GENERATION_TYPE_LABELS[t]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {genType === "BULK" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label htmlFor="cg-qty">Quantidade</Label>
                <Input id="cg-qty" type="number" min="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cg-prefix">Prefixo (opc)</Label>
                <Input id="cg-prefix" value={prefix} onChange={(e) => setPrefix(e.target.value)} />
              </div>
            </div>
          )}

          {genType === "SINGLE_USE" && (
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label htmlFor="cg-code">Código (opc)</Label>
                <Input id="cg-code" value={code} onChange={(e) => setCode(e.target.value)} placeholder="Gerado se vazio" />
              </div>
              <div className="space-y-1">
                <Label htmlFor="cg-prefix2">Prefixo (opc)</Label>
                <Input id="cg-prefix2" value={prefix} onChange={(e) => setPrefix(e.target.value)} />
              </div>
            </div>
          )}

          {genType === "PER_CUSTOMER" && (
            <div className="space-y-1">
              <Label>Cliente *</Label>
              <CustomerAutocomplete
                value={customerId || null}
                onChange={(id) => setCustomerId(id)}
                placeholder="Selecionar cliente…"
              />
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="cg-max">Máx. usos por cupom</Label>
              <Input
                id="cg-max"
                type="number"
                min="1"
                value={maxUses}
                onChange={(e) => setMaxUses(e.target.value)}
                disabled={genType === "SINGLE_USE"}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="cg-exp">Validade (opc)</Label>
              <DateTimePicker id="cg-exp" value={expiresAt} onChange={setExpiresAt} />
            </div>
          </div>

          <div className="space-y-1">
            <Label>Reabertura</Label>
            <Select value={reopen} onValueChange={(v) => v && setReopen(v)}>
              <SelectTrigger className="w-full"><SelectValue>{COUPON_REOPEN_LABELS[reopen]}</SelectValue></SelectTrigger>
              <SelectContent>
                {Object.keys(COUPON_REOPEN_LABELS).map((r) => (
                  <SelectItem key={r} value={r}>{COUPON_REOPEN_LABELS[r]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleGenerate} disabled={saving}>{saving ? "Gerando…" : "Gerar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export default function CouponsPage() {
  const { id } = useParams<{ id: string }>()

  const [promotion, setPromotion] = useState<Promotion | null>(null)
  const [coupons, setCoupons] = useState<Coupon[]>([])
  const [customerMap, setCustomerMap] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [genOpen, setGenOpen] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const [promo, cps] = await Promise.all([
        api.get<Promotion>(`/promotions/${id}`),
        api.get<Coupon[]>(`/promotions/${id}/coupons`),
      ])
      setPromotion(promo)
      setCoupons(cps)
      if (cps.some((c) => c.customer_id)) {
        try {
          const custs = await api.get<Customer[]>("/customers/")
          setCustomerMap(new Map(custs.map((c) => [c.id, c.name])))
        } catch { /* nomes ficam como id */ }
      }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function copyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      toast.success(`Código ${code} copiado`)
    } catch {
      toast.error("Não foi possível copiar")
    }
  }

  return (
    <div className="space-y-6">
      <Link href="/promocoes" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft size={16} strokeWidth={1.5} /> Promoções
      </Link>

      <PageHeader
        eyebrow="Promoção"
        title={`Cupons${promotion ? ` · ${promotion.name}` : ""}`}
        description="Gere e gerencie cupons desta promoção."
      >
        {promotion && <PromotionBadge status={promotion.status} />}
        <Button onClick={() => setGenOpen(true)}>+ Gerar cupons</Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : coupons.length === 0 ? (
        <EmptyState title="Nenhum cupom" description="Gere cupons para esta promoção." />
      ) : (
        <div className="overflow-hidden rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Código</th>
                <th className="px-4 py-3 text-left font-medium">Tipo</th>
                <th className="px-4 py-3 text-left font-medium">Usos</th>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Validade</th>
                <th className="px-4 py-3 text-left font-medium">Reabertura</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {coupons.map((c) => (
                <tr key={c.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => copyCode(c.code)}
                      className="inline-flex items-center gap-1.5 font-mono text-xs hover:text-primary"
                      title="Copiar código"
                    >
                      {c.code}
                      <Copy className="h-3 w-3" />
                    </button>
                  </td>
                  <td className="px-4 py-3">{GENERATION_TYPE_LABELS[c.generation_type] ?? c.generation_type}</td>
                  <td className="px-4 py-3">{c.uses_count}{c.max_uses != null ? `/${c.max_uses}` : ""}</td>
                  <td className="px-4 py-3">
                    {c.customer_id ? (customerMap.get(c.customer_id) ?? c.customer_id) : "—"}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{c.expires_at ? formatDateTime(c.expires_at) : "—"}</td>
                  <td className="px-4 py-3">{COUPON_REOPEN_LABELS[c.coupon_reopen_policy] ?? c.coupon_reopen_policy}</td>
                  <td className="px-4 py-3"><CouponBadge status={c.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <GenerateCouponsDialog
        promotionId={id}
        open={genOpen}
        onOpenChange={setGenOpen}
        onGenerated={load}
      />
    </div>
  )
}
