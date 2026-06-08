"use client"

import { useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatBRL, formatDateTime } from "@/lib/utils"
import { PAYMENT_METHOD_LABELS } from "@/lib/constants"

interface Payment {
  payment_id: string
  customer_id: string | null
  appointment_id: string | null
  currency: string
  gross_catalog_amount: number
  discount_amount: number
  net_charged_amount: number
  provider_fee: number
  payment_method: string
  payment_submethod: string | null
  payment_source_id: string | null
  provider: string
  external_charge_id: string | null
  status: string
  manual_override_count: number
  created_at: string
  paid_at: string | null
  refunded_at: string | null
}

const REFUND_REASONS = [
  { value: "SERVICE_FAILURE",     label: "Falha no serviço" },
  { value: "REGISTRATION_ERROR",  label: "Erro de cadastro" },
  { value: "DEADLINE_POLICY",     label: "Política de prazo" },
  { value: "OTHER",               label: "Outro motivo" },
]

const STATUS_BADGE: Record<string, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
  PENDING:   { label: "Pendente",    variant: "secondary" },
  CONFIRMED: { label: "Confirmado",  variant: "default" },
  FAILED:    { label: "Falhou",      variant: "destructive" },
  CANCELLED: { label: "Cancelado",   variant: "outline" },
  REFUNDED:  { label: "Reembolsado", variant: "outline" },
}

export default function PaymentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const { role } = useAuth()
  const paymentId = params.id as string

  const [payment, setPayment] = useState<Payment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refundReason, setRefundReason] = useState<string | null>(null)
  const [refunding, setRefunding] = useState(false)
  const [refundError, setRefundError] = useState<string | null>(null)

  useEffect(() => {
    api.get<Payment>(`/payments/${paymentId}`)
      .then(setPayment)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [paymentId])

  const handleRefund = async () => {
    if (!refundReason) {
      setRefundError("Selecione o motivo do reembolso")
      return
    }
    setRefunding(true)
    setRefundError(null)
    try {
      const updated = await api.post<Payment>(`/payments/${paymentId}/refund`, { reason: refundReason })
      setPayment(updated)
    } catch (e: unknown) {
      setRefundError(e instanceof Error ? e.message : "Erro ao processar reembolso")
    } finally {
      setRefunding(false)
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Carregando...</p>
  }

  if (error || !payment) {
    return <p className="text-sm text-destructive">{error ?? "Pagamento não encontrado"}</p>
  }

  const badge = STATUS_BADGE[payment.status] ?? { label: payment.status, variant: "outline" as const }
  const canRefund = payment.status === "CONFIRMED" && (role === "OWNER" || role === "ADMIN")

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center gap-3">
        <button
          onClick={() => router.back()}
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          ← Voltar
        </button>
        <h1 className="text-3xl tracking-wide">Pagamento</h1>
        <Badge variant={badge.variant}>{badge.label}</Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Detalhes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <Row label="ID" value={payment.payment_id} mono />
          <Row
            label="Método"
            value={
              payment.payment_method === "MAQUININHA" && payment.payment_submethod
                ? PAYMENT_METHOD_LABELS[`MAQUININHA_${payment.payment_submethod}`] ?? PAYMENT_METHOD_LABELS.MAQUININHA
                : PAYMENT_METHOD_LABELS[payment.payment_method] ?? payment.payment_method
            }
          />
          <Row label="Provedor" value={payment.provider} />
          {payment.external_charge_id && (
            <Row label="Cobrança externa" value={payment.external_charge_id} mono />
          )}
          <Row label="Valor catálogo" value={formatBRL(payment.gross_catalog_amount)} />
          {payment.discount_amount > 0 && (
            <Row label="Desconto" value={`− ${formatBRL(payment.discount_amount)}`} />
          )}
          <Row label="Valor cobrado" value={formatBRL(payment.net_charged_amount)} bold />
          {payment.provider_fee > 0 && (
            <Row label="Taxa da operadora" value={formatBRL(payment.provider_fee)} />
          )}
          <Row label="Criado em" value={formatDateTime(payment.created_at)} />
          {payment.paid_at && (
            <Row label="Confirmado em" value={formatDateTime(payment.paid_at)} />
          )}
          {payment.refunded_at && (
            <Row label="Reembolsado em" value={formatDateTime(payment.refunded_at)} />
          )}
          {payment.customer_id && (
            <Row label="Cliente" value={payment.customer_id} mono />
          )}
          {payment.appointment_id && (
            <Row label="Agendamento" value={payment.appointment_id} mono />
          )}
        </CardContent>
      </Card>

      {canRefund && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base font-medium text-destructive">
              Reembolsar pagamento
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">Motivo do reembolso</label>
              <Select value={refundReason ?? ""} onValueChange={(v) => setRefundReason(v || null)}>
                <SelectTrigger className="w-full max-w-xs">
                  <SelectValue placeholder="Selecione o motivo" />
                </SelectTrigger>
                <SelectContent>
                  {REFUND_REASONS.map((r) => (
                    <SelectItem key={r.value} value={r.value}>
                      {r.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {refundError && (
              <p className="text-sm text-destructive">{refundError}</p>
            )}
            <Button
              variant="destructive"
              size="sm"
              onClick={handleRefund}
              disabled={refunding || !refundReason}
            >
              {refunding ? "Processando..." : `Reembolsar ${formatBRL(payment.net_charged_amount)}`}
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

function Row({
  label,
  value,
  mono = false,
  bold = false,
}: {
  label: string
  value: string
  mono?: boolean
  bold?: boolean
}) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted-foreground shrink-0">{label}</span>
      <span className={[mono ? "font-mono text-xs" : "", bold ? "font-semibold" : ""].join(" ")}>
        {value}
      </span>
    </div>
  )
}
