"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import type { Service } from "@/types"
import { formatBRLFromDecimal } from "@/lib/utils"
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
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

/* ============================ Deposit policies ============================ */

interface DepositPolicy {
  policy_id: string
  service_id: string | null
  deposit_type: "FIXED_AMOUNT" | "PERCENTAGE"
  deposit_value: string
  refundable_until_hours_before: number
  refund_on_tenant_fault: boolean
  retain_on_no_show: boolean
  commission_on_retained_deposit: boolean
}

interface PolicyForm {
  service_id: string
  deposit_type: "FIXED_AMOUNT" | "PERCENTAGE"
  deposit_value: string
  refundable_until_hours_before: string
  refund_on_tenant_fault: boolean
  retain_on_no_show: boolean
  commission_on_retained_deposit: boolean
}

const EMPTY_FORM: PolicyForm = {
  service_id: "global",
  deposit_type: "PERCENTAGE",
  deposit_value: "",
  refundable_until_hours_before: "24",
  refund_on_tenant_fault: true,
  retain_on_no_show: true,
  commission_on_retained_deposit: false,
}

function depositValueLabel(p: DepositPolicy) {
  return p.deposit_type === "PERCENTAGE"
    ? `${parseFloat(p.deposit_value)}%`
    : formatBRLFromDecimal(p.deposit_value)
}

function DepositPoliciesTab() {
  const [policies, setPolicies] = useState<DepositPolicy[]>([])
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.get<DepositPolicy[]>("/deposit-policies")
      setPolicies(data)
      try { setServices(await api.get<Service[]>("/services/")) } catch { /* opcional */ }
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally { setLoading(false) }
  }, [])
  useEffect(() => { load() }, [load])

  const serviceName = (sid: string | null) =>
    sid == null ? "Global" : services.find((s) => s.id === sid)?.name ?? sid.slice(0, 8)

  if (loading) return <Skeleton className="h-64 w-full" />
  if (error) return <ErrorState message={error} onRetry={load} />

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <PolicyDialog services={services} onSaved={load} />
      </div>
      {policies.length === 0 ? (
        <EmptyState title="Nenhuma política" description="Sem políticas de sinal — depósito desativado." />
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Serviço</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead className="text-right">Valor</TableHead>
                <TableHead className="text-right">Janela (h)</TableHead>
                <TableHead>Reter no NO_SHOW</TableHead>
                <TableHead className="w-32" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {policies.map((p) => (
                <TableRow key={p.policy_id}>
                  <TableCell>
                    {p.service_id == null
                      ? <Badge variant="secondary">Global</Badge>
                      : serviceName(p.service_id)}
                  </TableCell>
                  <TableCell>{p.deposit_type === "PERCENTAGE" ? "Percentual" : "Valor fixo"}</TableCell>
                  <TableCell className="text-right font-mono">{depositValueLabel(p)}</TableCell>
                  <TableCell className="text-right font-mono">{p.refundable_until_hours_before}</TableCell>
                  <TableCell>
                    <Badge variant={p.retain_on_no_show ? "default" : "outline"}>
                      {p.retain_on_no_show ? "Sim" : "Não"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right space-x-1">
                    <PolicyDialog services={services} onSaved={load} existing={p} />
                    <Tooltip>
                      <TooltipTrigger render={<span className="inline-flex" />}>
                        <Button size="sm" variant="ghost" disabled>Excluir</Button>
                      </TooltipTrigger>
                      <TooltipContent>Em breve</TooltipContent>
                    </Tooltip>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function PolicyDialog({
  services, onSaved, existing,
}: { services: Service[]; onSaved: () => void; existing?: DepositPolicy }) {
  const editing = !!existing
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState<PolicyForm>(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  function onOpenChange(v: boolean) {
    if (v) {
      setForm(existing ? {
        service_id: existing.service_id ?? "global",
        deposit_type: existing.deposit_type,
        deposit_value: String(parseFloat(existing.deposit_value)),
        refundable_until_hours_before: String(existing.refundable_until_hours_before),
        refund_on_tenant_fault: existing.refund_on_tenant_fault,
        retain_on_no_show: existing.retain_on_no_show,
        commission_on_retained_deposit: existing.commission_on_retained_deposit,
      } : EMPTY_FORM)
    }
    setOpen(v)
  }

  async function handleSave() {
    if (!(parseFloat(form.deposit_value) > 0)) { toast.error("Informe um valor maior que zero."); return }
    setSaving(true)
    try {
      if (editing && existing) {
        await api.put(`/deposit-policies/${existing.policy_id}`, {
          deposit_type: form.deposit_type,
          deposit_value: Number(form.deposit_value),
          refundable_until_hours_before: Number(form.refundable_until_hours_before),
          refund_on_tenant_fault: form.refund_on_tenant_fault,
          retain_on_no_show: form.retain_on_no_show,
          commission_on_retained_deposit: form.commission_on_retained_deposit,
        })
        toast.success("Política atualizada")
      } else {
        await api.post("/deposit-policies", {
          service_id: form.service_id === "global" ? null : form.service_id,
          deposit_type: form.deposit_type,
          deposit_value: Number(form.deposit_value),
          refundable_until_hours_before: Number(form.refundable_until_hours_before),
          refund_on_tenant_fault: form.refund_on_tenant_fault,
          retain_on_no_show: form.retain_on_no_show,
          commission_on_retained_deposit: form.commission_on_retained_deposit,
        })
        toast.success("Política criada")
      }
      setOpen(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally { setSaving(false) }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger render={<Button size="sm" variant={editing ? "outline" : "default"} />}>
        {editing ? "Editar" : "+ Nova política"}
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>{editing ? "Editar política" : "Nova política de sinal"}</DialogTitle></DialogHeader>
        <div className="space-y-4 py-1">
          {!editing && (
            <div className="space-y-1">
              <Label>Serviço</Label>
              <Select value={form.service_id} onValueChange={(v) => v && setForm({ ...form, service_id: v })}>
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {form.service_id === "global" ? "Global (todos)" : services.find((s) => s.id === form.service_id)?.name ?? "Serviço"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="global">Global (todos)</SelectItem>
                  {services.map((s) => <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <Label>Tipo</Label>
              <Select
                value={form.deposit_type}
                onValueChange={(v) => v && setForm({ ...form, deposit_type: v as PolicyForm["deposit_type"] })}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{form.deposit_type === "PERCENTAGE" ? "Percentual" : "Valor fixo"}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PERCENTAGE">Percentual</SelectItem>
                  <SelectItem value="FIXED_AMOUNT">Valor fixo</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="pf-value">{form.deposit_type === "PERCENTAGE" ? "Valor (%)" : "Valor (R$)"}</Label>
              <Input id="pf-value" type="number" min={0} step="0.01" value={form.deposit_value}
                onChange={(e) => setForm({ ...form, deposit_value: e.target.value })} />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="pf-window">Janela de cancelamento (horas antes)</Label>
            <Input id="pf-window" type="number" min={0} value={form.refundable_until_hours_before}
              onChange={(e) => setForm({ ...form, refundable_until_hours_before: e.target.value })} className="w-40" />
          </div>
          <ToggleRow label="Reembolsar em falha do estabelecimento"
            checked={form.refund_on_tenant_fault} onChange={(v) => setForm({ ...form, refund_on_tenant_fault: v })} />
          <ToggleRow label="Reter sinal em NO_SHOW"
            checked={form.retain_on_no_show} onChange={(v) => setForm({ ...form, retain_on_no_show: v })} />
          <ToggleRow label="Comissão sobre sinal retido"
            checked={form.commission_on_retained_deposit} onChange={(v) => setForm({ ...form, commission_on_retained_deposit: v })} />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
          <Button onClick={handleSave} disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ToggleRow({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="flex items-center justify-between">
      <Label className="font-normal">{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

/* ============================ Asaas status ============================ */

interface FinancialSettings {
  payment_provider: string | null
  external_account_id: string | null
  external_account_status: string | null
  external_account_created_at: string | null
  accounts_count: number
}

function AsaasStatusBanner({ status }: { status: string | null }) {
  if (status === "active") {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm">
        <p className="font-medium text-foreground">Subconta Asaas ativa</p>
        <p className="text-muted-foreground mt-1">Sua conta de pagamentos está ativa e pronta para receber cobranças.</p>
      </div>
    )
  }
  if (status === "pending_verification") {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm">
        <p className="font-medium text-foreground">Subconta Asaas em análise</p>
        <p className="text-muted-foreground mt-1">
          Sua conta está sendo verificada pela Asaas (até 2 dias úteis). Você será notificado quando aprovada.
        </p>
      </div>
    )
  }
  if (status === "suspended") {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm">
        <p className="font-medium text-foreground">Subconta Asaas suspensa</p>
        <p className="text-muted-foreground mt-1">Entre em contato com o suporte Asaas para mais informações.</p>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm">
      <p className="font-medium text-foreground">Pagamentos online não configurados</p>
      <p className="text-muted-foreground mt-1">A subconta de pagamentos ainda não foi criada. Contate o suporte Paladino.</p>
    </div>
  )
}

function AsaasTab() {
  const [data, setData] = useState<FinancialSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setData(await api.get<FinancialSettings>("/financial/settings"))
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])
  useEffect(() => { load() }, [load])

  if (loading) return <Skeleton className="h-48 w-full" />
  if (error || !data) return <ErrorState message={error ?? undefined} onRetry={load} />

  return (
    <Card className="max-w-2xl">
      <CardHeader><CardTitle>Status da subconta Asaas</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <AsaasStatusBanner status={data.external_account_status} />
        {data.external_account_id && (
          <div className="text-sm text-muted-foreground space-y-1 pt-2 border-t border-border">
            <p><span className="text-foreground font-medium">ID da conta:</span> {data.external_account_id}</p>
            {data.external_account_created_at && (
              <p><span className="text-foreground font-medium">Criada em:</span> {new Date(data.external_account_created_at).toLocaleDateString("pt-BR")}</p>
            )}
            <p><span className="text-foreground font-medium">Contas financeiras:</span> {data.accounts_count}</p>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/* ============================ Page ============================ */

export default function FinancialSettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Configurações financeiras" description="Políticas de sinal e status de pagamentos." />
      <Tabs defaultValue="policies">
        <TabsList>
          <TabsTrigger value="policies">Políticas de sinal</TabsTrigger>
          <TabsTrigger value="asaas">Status Asaas</TabsTrigger>
        </TabsList>
        <TabsContent value="policies"><DepositPoliciesTab /></TabsContent>
        <TabsContent value="asaas"><AsaasTab /></TabsContent>
      </Tabs>
    </div>
  )
}
