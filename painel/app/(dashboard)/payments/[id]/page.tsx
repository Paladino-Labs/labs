"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { PaymentBadge } from "@/components/FsmBadge"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { formatBRL, formatDateTime } from "@/lib/utils"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"

interface Payment {
  payment_id: string
  customer_id: string | null
  appointment_id: string | null
  gross_catalog_amount: number
  discount_amount: number
  net_charged_amount: number
  provider_fee: number
  payment_method: string
  payment_submethod: string | null
  provider: string
  external_charge_id: string | null
  status: string
  manual_override_count: number
  coupon_code: string | null
  created_at: string
  paid_at: string | null
  refunded_at: string | null
}

interface ConfirmResponse {
  payment?: Payment
  fee_warning?: { fee_source: string; message: string } | null
}

const REFUND_REASONS = [
  { value: "SERVICE_FAILURE",    label: "Falha no serviço" },
  { value: "REGISTRATION_ERROR", label: "Erro de cadastro" },
  { value: "DEADLINE_POLICY",    label: "Política de prazo" },
  { value: "OTHER",              label: "Outro motivo" },
]

function methodLabel(p: Payment) {
  return p.payment_method === "MAQUININHA" && p.payment_submethod
    ? PAYMENT_METHOD_LABELS[`MAQUININHA_${p.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
    : PAYMENT_METHOD_LABELS[p.payment_method] ?? p.payment_method
}

export default function PaymentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { role } = useAuth()

  const [payment, setPayment] = useState<Payment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setPayment(await api.get<Payment>(`/payments/${id}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally { setLoading(false) }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="space-y-6 max-w-2xl">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }
  if (error || !payment) {
    return (
      <div className="space-y-4 max-w-2xl">
        <Button variant="outline" size="sm" onClick={() => router.back()}>← Voltar</Button>
        <ErrorState message={error ?? "Pagamento não encontrado."} onRetry={load} />
      </div>
    )
  }

  const isOwner = role === "OWNER"
  const isAdmin = role === "ADMIN"
  const canManage = isOwner || isAdmin
  const isPending = payment.status === "PENDING"
  const isConfirmed = payment.status === "CONFIRMED"

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <button onClick={() => router.back()} className="hover:text-foreground">← Voltar</button>
      </div>

      <PageHeader eyebrow={`Pagamento · ${payment.payment_id.slice(0, 8)}`} title="Detalhe do pagamento">
        <PaymentBadge status={payment.status} />
      </PageHeader>

      <Card>
        <CardHeader><CardTitle>Valores</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="Bruto (catálogo)" value={formatBRL(payment.gross_catalog_amount)} />
          {payment.discount_amount > 0 && (
            <Row label="Desconto" value={`− ${formatBRL(payment.discount_amount)}`} />
          )}
          <Row label="Líquido cobrado" value={formatBRL(payment.net_charged_amount)} bold />
          {payment.provider_fee > 0 && (
            <Row label="Taxa da operadora" value={formatBRL(payment.provider_fee)} />
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Origem</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="Método" value={methodLabel(payment)} />
          <Row label="Provedor" value={payment.provider} />
          {payment.coupon_code && <Row label="Cupom" value={payment.coupon_code} />}
          {payment.external_charge_id && <Row label="Cobrança externa" value={payment.external_charge_id} mono />}
          {payment.appointment_id && (
            <div className="flex justify-between gap-4">
              <span className="text-muted-foreground shrink-0">Agendamento</span>
              <Link href={`/appointments/${payment.appointment_id}`} className="text-primary hover:underline font-mono text-xs">
                {payment.appointment_id.slice(0, 8)}
              </Link>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Datas</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="Criado em" value={formatDateTime(payment.created_at)} />
          {payment.paid_at && <Row label="Confirmado em" value={formatDateTime(payment.paid_at)} />}
          {payment.refunded_at && <Row label="Estornado em" value={formatDateTime(payment.refunded_at)} />}
        </CardContent>
      </Card>

      {/* Ações */}
      {(isPending || isConfirmed) && (
        <Card>
          <CardHeader><CardTitle>Ações</CardTitle></CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {isPending && <ConfirmDialog payment={payment} onDone={load} />}
            {isPending && canManage && <DiscountDialog payment={payment} onDone={load} />}
            {isConfirmed && canManage && <RefundDialog payment={payment} isOwner={isOwner} onDone={load} />}
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function ConfirmDialog({ payment, onDone }: { payment: Payment; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handle() {
    setBusy(true)
    try {
      const res = await api.post<ConfirmResponse>(`/payments/${payment.payment_id}/confirm-manual`, {
        payment_submethod: payment.payment_submethod,
      })
      setOpen(false)
      toast.success("Pagamento confirmado")
      if (res?.fee_warning) {
        toast.warning(`${res.fee_warning.fee_source}: ${res.fee_warning.message}`)
      }
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao confirmar")
    } finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>Confirmar manualmente</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirmar pagamento</DialogTitle>
          <DialogDescription>Confirma o recebimento de {formatBRL(payment.net_charged_amount)}?</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handle} disabled={busy}>{busy ? "Confirmando…" : "Confirmar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function DiscountDialog({ payment, onDone }: { payment: Payment; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [amount, setAmount] = useState("")
  const [reason, setReason] = useState("")
  const [busy, setBusy] = useState(false)

  async function handle() {
    const value = parseFloat(amount)
    if (!(value > 0)) { toast.error("Informe um valor maior que zero."); return }
    if (!reason.trim()) { toast.error("Informe o motivo."); return }
    setBusy(true)
    try {
      await api.post(`/payments/${payment.payment_id}/manual-discount`, {
        discount_amount: value,
        reason,
      })
      setOpen(false); setAmount(""); setReason("")
      toast.success("Desconto aplicado")
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao aplicar desconto")
    } finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="outline" />}>Aplicar desconto</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Desconto manual</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label htmlFor="d-amount">Valor do desconto (R$) *</Label>
            <Input id="d-amount" type="number" min={0} step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="d-reason">Motivo *</Label>
            <Textarea id="d-reason" value={reason} onChange={(e) => setReason(e.target.value)} rows={2} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handle} disabled={busy}>{busy ? "Aplicando…" : "Aplicar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RefundDialog({ payment, isOwner, onDone }: { payment: Payment; isOwner: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false)
  const [reason, setReason] = useState<string | null>(null)
  const [forceLocal, setForceLocal] = useState(false)
  const [busy, setBusy] = useState(false)

  async function handle() {
    if (!reason) { toast.error("Selecione o motivo do estorno."); return }
    setBusy(true)
    try {
      await api.post(`/payments/${payment.payment_id}/refund`, {
        reason,
        ...(isOwner && forceLocal ? { force_local: true } : {}),
      })
      setOpen(false)
      toast.success("Pagamento estornado")
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao estornar")
    } finally { setBusy(false) }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button variant="destructive" />}>Estornar</DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Estornar pagamento</DialogTitle>
          <DialogDescription>Estorno de {formatBRL(payment.net_charged_amount)}.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-1">
          <div className="space-y-1">
            <Label>Motivo *</Label>
            <Select value={reason ?? ""} onValueChange={(v) => setReason(v || null)}>
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Selecione o motivo">
                  {reason ? REFUND_REASONS.find((r) => r.value === reason)?.label : "Selecione o motivo"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {REFUND_REASONS.map((r) => (
                  <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {isOwner && (
            <>
              <Separator />
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={forceLocal}
                  onChange={(e) => setForceLocal(e.target.checked)}
                  className="size-4 accent-primary"
                />
                Forçar estorno local (sem chamada ao provedor)
              </label>
            </>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="destructive" onClick={handle} disabled={busy || !reason}>
            {busy ? "Estornando…" : "Confirmar estorno"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Row({ label, value, mono = false, bold = false }: { label: string; value: string; mono?: boolean; bold?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={[mono ? "font-mono text-xs" : "", bold ? "font-semibold" : ""].join(" ")}>{value}</span>
    </div>
  )
}
