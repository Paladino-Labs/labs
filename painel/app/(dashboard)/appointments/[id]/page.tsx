"use client"

import { useCallback, useEffect, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import { toast } from "sonner"
import { ArrowLeft, Check, X, CalendarClock, Play, UserX } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { Appointment } from "@/types"
import { formatBRLFromDecimal, formatDateTime } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { AppointmentBadge, PaymentBadge } from "@/components/FsmBadge"
import { PendingProductsNotice } from "@/components/PendingProductsNotice"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Separator } from "@/components/ui/separator"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

interface Payment {
  payment_id: string
  appointment_id: string | null
  net_charged_amount: number | string
  status: string
  provider: string
}

export default function AppointmentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const { role } = useAuth()
  const isProfessional = role === "PROFESSIONAL"

  const [appt, setAppt] = useState<Appointment | null>(null)
  const [deposit, setDeposit] = useState<Payment | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<Appointment>(`/appointments/${id}`)
      setAppt(data)
      // Sinal/depósito: Payment manual vinculado a este agendamento.
      try {
        const payments = await api.get<Payment[]>("/payments")
        const dep = payments.find(
          (p) => p.appointment_id === id && p.provider === "manual",
        )
        setDeposit(dep ?? null)
      } catch {
        setDeposit(null)
      }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
          <Skeleton className="h-64 w-full" />
        </div>
      </div>
    )
  }

  if (error || !appt) {
    return (
      <div className="space-y-4">
        <Button variant="outline" size="sm" onClick={() => router.back()}>← Voltar</Button>
        <ErrorState message={error ?? "Operação não encontrada."} onRetry={load} />
      </div>
    )
  }

  const depositAmount = deposit ? Number(deposit.net_charged_amount) : 0
  const balance = (parseFloat(appt.total_amount) - depositAmount).toFixed(2)

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <button onClick={() => router.back()} className="inline-flex items-center gap-1 hover:text-foreground">
          <ArrowLeft size={16} strokeWidth={1.5} /> Voltar
        </button>
      </div>

      <PageHeader
        eyebrow={`Operação · ${appt.id.slice(0, 8)}`}
        title={appt.customer?.name ?? "Cliente"}
        description={`${formatDateTime(appt.start_at)} → ${formatDateTime(appt.end_at)}`}
      >
        <AppointmentBadge status={appt.status} />
        {!isProfessional && <ActionButtons appt={appt} onDone={load} />}
      </PageHeader>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader><CardTitle className="font-display text-xl">Serviço(s)</CardTitle></CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead className="w-28 text-right">Duração</TableHead>
                    <TableHead className="w-32 text-right">Preço</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {appt.services.map((s) => (
                    <TableRow key={s.id}>
                      <TableCell>{s.service_name}</TableCell>
                      <TableCell className="text-right text-muted-foreground">
                        {Math.round(Number(s.duration_snapshot))} min
                      </TableCell>
                      <TableCell className="text-right font-mono">{formatBRLFromDecimal(s.price_snapshot)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="font-display text-xl">Profissional</CardTitle></CardHeader>
            <CardContent>
              <p className="text-sm text-foreground">{appt.professional?.name ?? "—"}</p>
              {appt.customer?.phone && (
                <p className="text-xs text-muted-foreground mt-1">Contato do cliente: {appt.customer.phone}</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="font-display text-xl">Valores</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-3 gap-4 text-sm">
                <div>
                  <dt className="text-muted-foreground">Subtotal</dt>
                  <dd className="font-mono">{formatBRLFromDecimal(appt.subtotal_amount)}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Desconto</dt>
                  <dd className="font-mono">{formatBRLFromDecimal(appt.discount_amount ?? "0")}</dd>
                </div>
                <div>
                  <dt className="text-muted-foreground">Total</dt>
                  <dd className="font-mono text-base">{formatBRLFromDecimal(appt.total_amount)}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          {deposit && (
            <Card>
              <CardHeader><CardTitle className="font-display text-xl">Sinal / Depósito</CardTitle></CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Sinal pago</span>
                  <span className="font-mono">{formatBRLFromDecimal(String(depositAmount))}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Status</span>
                  <PaymentBadge status={deposit.status} />
                </div>
                <Separator />
                <div className="flex items-center justify-between">
                  <span className="text-sm text-muted-foreground">Saldo pendente</span>
                  <span className="font-mono">{formatBRLFromDecimal(balance)}</span>
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader><CardTitle className="font-display text-xl">Estado</CardTitle></CardHeader>
            <CardContent>
              <ol className="relative space-y-4 border-l border-border pl-4">
                <li className="relative">
                  <span className="absolute -left-[21px] top-1 size-2 rounded-full bg-muted-foreground/40" />
                  <p className="text-sm font-medium">Agendado</p>
                  <p className="text-xs text-muted-foreground">{formatDateTime(appt.start_at)}</p>
                </li>
                <li className="relative">
                  <span className="absolute -left-[21px] top-1 size-2 rounded-full bg-primary" />
                  <p className="text-sm">
                    Estado atual: <span className="font-medium"><AppointmentBadge status={appt.status} /></span>
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Financeiro: {appt.financial_status}
                  </p>
                </li>
              </ol>
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  )
}

function ActionButtons({ appt, onDone }: { appt: Appointment; onDone: () => void }) {
  const [completeOpen, setCompleteOpen] = useState(false)
  const [cancelOpen, setCancelOpen] = useState(false)
  const [rescheduleOpen, setRescheduleOpen] = useState(false)
  const [cancelReason, setCancelReason] = useState("")
  const [newDate, setNewDate] = useState("")
  const [busy, setBusy] = useState(false)

  const canComplete = appt.status === "SCHEDULED" || appt.status === "IN_PROGRESS"
  const canCancel = appt.status === "SCHEDULED" || appt.status === "IN_PROGRESS"

  async function run(fn: () => Promise<unknown>, successMsg: string, close: () => void) {
    setBusy(true)
    try {
      await fn()
      close()
      toast.success(successMsg)
      onDone()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro inesperado")
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <Dialog open={completeOpen} onOpenChange={setCompleteOpen}>
        <DialogTrigger render={<Button size="sm" disabled={!canComplete} />}>
          <Check size={16} strokeWidth={1.5} /> Concluir
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Concluir operação</DialogTitle>
            <DialogDescription>
              Confirma a conclusão deste atendimento? Isso dispara a cobrança / saldo.
            </DialogDescription>
          </DialogHeader>
          {/* Produtos a retirar (Sprint C) — informativo, não bloqueia */}
          <PendingProductsNotice appointmentId={appt.id} />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompleteOpen(false)}>Cancelar</Button>
            <Button
              disabled={busy}
              onClick={() => run(
                () => api.patch(`/appointments/${appt.id}/complete`, {}),
                "Atendimento concluído",
                () => setCompleteOpen(false),
              )}
            >
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogTrigger render={<Button size="sm" variant="outline" disabled={!canCancel} />}>
          <X size={16} strokeWidth={1.5} /> Cancelar
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar operação</DialogTitle>
            <DialogDescription>Informe o motivo do cancelamento (opcional).</DialogDescription>
          </DialogHeader>
          <Textarea
            value={cancelReason}
            onChange={(e) => setCancelReason(e.target.value)}
            placeholder="Motivo"
            rows={3}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setCancelOpen(false)}>Voltar</Button>
            <Button
              variant="destructive"
              disabled={busy}
              onClick={() => run(
                () => api.patch(`/appointments/${appt.id}/cancel`, { reason: cancelReason || undefined }),
                "Operação cancelada",
                () => { setCancelOpen(false); setCancelReason("") },
              )}
            >
              Confirmar cancelamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={rescheduleOpen} onOpenChange={setRescheduleOpen}>
        <DialogTrigger render={<Button size="sm" variant="outline" disabled={!canCancel} />}>
          <CalendarClock size={16} strokeWidth={1.5} /> Remarcar
        </DialogTrigger>
        <DialogContent>
          <DialogHeader><DialogTitle>Remarcar</DialogTitle></DialogHeader>
          <div className="space-y-2">
            <Label htmlFor="newDate">Novo horário</Label>
            <Input
              id="newDate"
              type="datetime-local"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRescheduleOpen(false)}>Cancelar</Button>
            <Button
              disabled={busy || !newDate}
              onClick={() => run(
                () => api.patch(`/appointments/${appt.id}/reschedule`, {
                  start_at: new Date(newDate).toISOString(),
                }),
                "Operação remarcada",
                () => { setRescheduleOpen(false); setNewDate("") },
              )}
            >
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Tooltip>
        <TooltipTrigger render={<span className="inline-flex" />}>
          <Button size="sm" variant="ghost" disabled>
            <Play size={16} strokeWidth={1.5} /> Iniciar
          </Button>
        </TooltipTrigger>
        <TooltipContent>Em breve</TooltipContent>
      </Tooltip>
      <Tooltip>
        <TooltipTrigger render={<span className="inline-flex" />}>
          <Button size="sm" variant="ghost" disabled>
            <UserX size={16} strokeWidth={1.5} /> No-show
          </Button>
        </TooltipTrigger>
        <TooltipContent>Em breve</TooltipContent>
      </Tooltip>
    </>
  )
}
