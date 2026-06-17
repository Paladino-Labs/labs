"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { PencilIcon, Trash2Icon, PlusIcon, Lock } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { formatBRL } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

// ─── Types ───────────────────────────────────────────────────────────────────

interface CommissionPolicyResponse {
  policy_id: string
  professional_id: string | null
  service_id: string | null
  commission_base: string
  commission_fee_policy: string
  rate: number | string | null
  fixed_amount: number | string | null
  is_active: boolean
  created_at: string
}

interface Professional { id: string; name: string }
interface Service { id: string; name: string; price: number }

// ─── Constants ───────────────────────────────────────────────────────────────

const BASE_LABELS: Record<string, string> = {
  GROSS_SERVICE:   "Percentual sobre valor bruto",
  CUSTOM_AMOUNT:   "Valor fixo (R$)",
  // Legados — exibidos apenas na tabela para dados históricos
  NET_SERVICE:     "% sobre valor líquido (legado)",
  GROSS_OPERATION: "% sobre operação bruta (legado)",
}

const FEE_POLICY_LABELS: Record<string, string> = {
  BARBERSHOP_PAYS: "Barbearia paga a taxa",
  SPLIT_50_50:     "Taxa dividida (50/50)",
  BARBER_PAYS:     "Barbeiro paga a taxa",
  // Legados — exibidos apenas na tabela para dados históricos
  BEFORE_FEES:     "Antes das taxas (legado)",
  AFTER_FEES:      "Após as taxas (legado)",
}

// Apenas opções Stage 0 — usadas nos formulários de criação/edição
const BASE_OPTIONS: [string, string][] = [
  ["GROSS_SERVICE", BASE_LABELS.GROSS_SERVICE],
  ["CUSTOM_AMOUNT", BASE_LABELS.CUSTOM_AMOUNT],
]
const FEE_OPTIONS: [string, string][] = [
  ["BARBERSHOP_PAYS", FEE_POLICY_LABELS.BARBERSHOP_PAYS],
  ["SPLIT_50_50",     FEE_POLICY_LABELS.SPLIT_50_50],
  ["BARBER_PAYS",     FEE_POLICY_LABELS.BARBER_PAYS],
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatRate(policy: CommissionPolicyResponse): string {
  if (policy.commission_base === "CUSTOM_AMOUNT" && policy.fixed_amount !== null)
    return formatBRL(Number(policy.fixed_amount))
  if (policy.rate !== null)
    return `${Number(policy.rate).toFixed(2)}%`
  return "—"
}

function isGlobal(p: CommissionPolicyResponse) {
  return p.professional_id === null && p.service_id === null
}

// ─── Empty form state ─────────────────────────────────────────────────────────

interface FormState {
  professional_id: string   // "" = todos
  service_id: string        // "" = todos
  commission_base: string
  commission_fee_policy: string
  amount: string            // rate or fixed_amount depending on base
}

const EMPTY_FORM: FormState = {
  professional_id:     "",
  service_id:          "",
  commission_base:     "GROSS_SERVICE",
  commission_fee_policy: "BARBERSHOP_PAYS",
  amount:              "",
}

// ─── Component ───────────────────────────────────────────────────────────────

export default function PoliticasPage() {
  const { role, hydrated } = useAuth()

  const [policies,      setPolicies]      = useState<CommissionPolicyResponse[]>([])
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [services,      setServices]      = useState<Service[]>([])
  const [loading,       setLoading]       = useState(true)
  const [error,         setError]         = useState<string | null>(null)

  // Global policy inline form
  const [globalForm,   setGlobalForm]   = useState<FormState>(EMPTY_FORM)
  const [globalSaving, setGlobalSaving] = useState(false)

  // Modal
  const [modalOpen,    setModalOpen]    = useState(false)
  const [editingPolicy, setEditingPolicy] = useState<CommissionPolicyResponse | null>(null)
  const [modalForm,    setModalForm]    = useState<FormState>(EMPTY_FORM)
  const [modalSaving,  setModalSaving]  = useState(false)

  // Confirm delete
  const [deleteTarget, setDeleteTarget] = useState<CommissionPolicyResponse | null>(null)
  const [deleting,     setDeleting]     = useState(false)

  const canAccess = role === "OWNER" || role === "ADMIN"

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [pols, profs, svcs] = await Promise.all([
        api.get<CommissionPolicyResponse[]>("/commission-policies"),
        api.get<Professional[]>("/professionals"),
        api.get<Service[]>("/services"),
      ])
      setPolicies(pols)
      setProfessionals(profs)
      setServices(svcs)

      // Pre-fill global form if policy exists
      const global = pols.find((p) => isGlobal(p) && p.is_active)
      if (global) {
        setGlobalForm({
          professional_id:      "",
          service_id:           "",
          commission_base:      global.commission_base,
          commission_fee_policy: global.commission_fee_policy,
          amount:
            global.commission_base === "CUSTOM_AMOUNT"
              ? global.fixed_amount !== null ? String(Number(global.fixed_amount)) : ""
              : global.rate !== null ? String(Number(global.rate)) : "",
        })
      } else {
        setGlobalForm(EMPTY_FORM)
      }
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao carregar")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!hydrated || !canAccess) return
    loadAll()
  }, [canAccess, hydrated, loadAll])

  // ── Derived data ────────────────────────────────────────────────────────────

  const activeGlobal   = policies.find((p) => isGlobal(p) && p.is_active) ?? null
  const specificActive = policies.filter((p) => !isGlobal(p) && p.is_active)

  const profName = (id: string | null) =>
    id === null ? "Todos os barbeiros" : (professionals.find((p) => p.id === id)?.name ?? id)
  const svcName  = (id: string | null) =>
    id === null ? "Todos os serviços"  : (services.find((s) => s.id === id)?.name ?? id)

  // ── Global save ─────────────────────────────────────────────────────────────

  async function handleGlobalSave() {
    setGlobalSaving(true)
    const isCustom = globalForm.commission_base === "CUSTOM_AMOUNT"
    const body = {
      commission_base:      globalForm.commission_base,
      commission_fee_policy: globalForm.commission_fee_policy,
      rate:         isCustom ? null : globalForm.amount !== "" ? Number(globalForm.amount) : null,
      fixed_amount: isCustom ? (globalForm.amount !== "" ? Number(globalForm.amount) : null) : null,
    }
    try {
      if (activeGlobal) {
        await api.patch(`/commission-policies/${activeGlobal.policy_id}`, body)
      } else {
        await api.post("/commission-policies", { ...body, professional_id: null, service_id: null })
      }
      toast.success("Regra geral salva")
      await loadAll()
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao salvar")
    } finally {
      setGlobalSaving(false)
    }
  }

  // ── Modal helpers ────────────────────────────────────────────────────────────

  function openCreate() {
    setEditingPolicy(null)
    setModalForm(EMPTY_FORM)
    setModalOpen(true)
  }

  function openEdit(policy: CommissionPolicyResponse) {
    setEditingPolicy(policy)
    setModalForm({
      professional_id:      policy.professional_id ?? "",
      service_id:           policy.service_id ?? "",
      commission_base:      policy.commission_base,
      commission_fee_policy: policy.commission_fee_policy,
      amount:
        policy.commission_base === "CUSTOM_AMOUNT"
          ? policy.fixed_amount !== null ? String(Number(policy.fixed_amount)) : ""
          : policy.rate !== null ? String(Number(policy.rate)) : "",
    })
    setModalOpen(true)
  }

  async function handleModalSave() {
    setModalSaving(true)
    const isCustom = modalForm.commission_base === "CUSTOM_AMOUNT"
    const body = {
      professional_id:      modalForm.professional_id !== "" ? modalForm.professional_id : null,
      service_id:           modalForm.service_id      !== "" ? modalForm.service_id      : null,
      commission_base:      modalForm.commission_base,
      commission_fee_policy: modalForm.commission_fee_policy,
      rate:         isCustom ? null : modalForm.amount !== "" ? Number(modalForm.amount) : null,
      fixed_amount: isCustom ? (modalForm.amount !== "" ? Number(modalForm.amount) : null) : null,
    }
    try {
      if (editingPolicy) {
        await api.patch(`/commission-policies/${editingPolicy.policy_id}`, body)
      } else {
        await api.post("/commission-policies", body)
      }
      toast.success(editingPolicy ? "Regra atualizada" : "Regra criada")
      setModalOpen(false)
      await loadAll()
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao salvar")
    } finally {
      setModalSaving(false)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/commission-policies/${deleteTarget.policy_id}`)
      toast.success("Regra removida")
      setDeleteTarget(null)
      await loadAll()
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao excluir")
    } finally {
      setDeleting(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  if (!hydrated) return null

  if (!canAccess) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Financeiro" title="Regras de comissão" />
        <EmptyState icon={<Lock size={28} strokeWidth={1.5} />} title="Acesso restrito"
          description="Disponível apenas para Proprietário e Administrador." />
      </div>
    )
  }

  return (
    <div className="max-w-4xl space-y-8">
      <PageHeader
        eyebrow="Financeiro"
        title="Regras de comissão"
        description="Configure como as comissões são calculadas para cada barbeiro e serviço."
      />

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={loadAll} />
      ) : (
        <>
          {/* ── Seção 1: Política global ── */}
          <Card>
            <CardHeader>
              <CardTitle>Regra geral</CardTitle>
              <p className="text-xs text-muted-foreground">
                Aplicada quando não há regra específica para o barbeiro ou serviço.
              </p>
            </CardHeader>
            <CardContent>
              <GlobalForm
                form={globalForm}
                onChange={setGlobalForm}
                onSave={handleGlobalSave}
                saving={globalSaving}
                hasExisting={activeGlobal !== null}
              />
            </CardContent>
          </Card>

          {/* ── Seção 2: Políticas específicas ── */}
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <div>
                <CardTitle>Regras específicas</CardTitle>
                <p className="mt-1 text-xs text-muted-foreground">
                  Substituem a regra global para combinações específicas de barbeiro/serviço.
                </p>
              </div>
              <Button size="sm" onClick={openCreate}>
                <PlusIcon className="mr-1.5 size-4" />
                Nova regra
              </Button>
            </CardHeader>
            <CardContent className={specificActive.length === 0 ? "" : "p-0"}>
              {specificActive.length === 0 ? (
                <EmptyState title="Nenhuma regra específica" description="A regra geral será aplicada a todos." />
              ) : (
                <div className="overflow-x-auto rounded-lg border border-border">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50 text-muted-foreground">
                      <tr>
                        <th className="px-4 py-3 text-left font-medium">Profissional</th>
                        <th className="px-4 py-3 text-left font-medium">Serviço</th>
                        <th className="px-4 py-3 text-left font-medium">Base</th>
                        <th className="px-4 py-3 text-left font-medium">Taxa</th>
                        <th className="px-4 py-3 text-left font-medium">Quem paga</th>
                        <th className="px-4 py-3 text-right font-medium">Ações</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {specificActive.map((policy) => (
                        <tr key={policy.policy_id} className="transition-colors hover:bg-muted/30">
                          <td className="px-4 py-3 font-medium">{profName(policy.professional_id)}</td>
                          <td className="px-4 py-3">{svcName(policy.service_id)}</td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {BASE_LABELS[policy.commission_base] ?? policy.commission_base}
                          </td>
                          <td className="px-4 py-3 font-medium">{formatRate(policy)}</td>
                          <td className="px-4 py-3 text-muted-foreground">
                            {FEE_POLICY_LABELS[policy.commission_fee_policy] ?? policy.commission_fee_policy}
                          </td>
                          <td className="px-4 py-3">
                            <div className="flex items-center justify-end gap-1">
                              <Button size="icon-sm" variant="ghost" onClick={() => openEdit(policy)} aria-label="Editar">
                                <PencilIcon className="size-4" />
                              </Button>
                              <Button size="icon-sm" variant="ghost"
                                className="text-destructive hover:text-destructive"
                                onClick={() => setDeleteTarget(policy)} aria-label="Excluir">
                                <Trash2Icon className="size-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* ── Modal criação/edição ── */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{editingPolicy ? "Editar regra" : "Nova regra específica"}</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Profissional */}
            <div className="space-y-1.5">
              <Label>Profissional</Label>
              <Select
                value={modalForm.professional_id}
                onValueChange={(v) => setModalForm((f) => ({ ...f, professional_id: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {modalForm.professional_id
                      ? professionals.find((p) => p.id === modalForm.professional_id)?.name ?? modalForm.professional_id
                      : "Todos os barbeiros"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Todos os barbeiros</SelectItem>
                  {professionals.map((p) => (
                    <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Serviço */}
            <div className="space-y-1.5">
              <Label>Serviço</Label>
              <Select
                value={modalForm.service_id}
                onValueChange={(v) => setModalForm((f) => ({ ...f, service_id: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {modalForm.service_id
                      ? services.find((s) => s.id === modalForm.service_id)?.name ?? modalForm.service_id
                      : "Todos os serviços"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="">Todos os serviços</SelectItem>
                  {services.map((s) => (
                    <SelectItem key={s.id} value={s.id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Base de cálculo */}
            <div className="space-y-1.5">
              <Label>Base de cálculo</Label>
              <Select
                value={modalForm.commission_base}
                onValueChange={(v) => setModalForm((f) => ({ ...f, commission_base: v ?? "", amount: "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{BASE_LABELS[modalForm.commission_base] ?? modalForm.commission_base}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {BASE_OPTIONS.map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Taxa / Valor fixo */}
            <div className="space-y-1.5">
              <Label htmlFor="modal-amount">
                {modalForm.commission_base === "CUSTOM_AMOUNT" ? "Valor fixo (R$)" : "Taxa (%)"}
              </Label>
              <Input
                id="modal-amount"
                type="number"
                step="0.01"
                min="0"
                value={modalForm.amount}
                onChange={(e) => setModalForm((f) => ({ ...f, amount: e.target.value }))}
                placeholder="0.00"
              />
            </div>

            {/* Quem paga a taxa do gateway */}
            <div className="space-y-1.5">
              <Label>Quem paga a taxa</Label>
              <Select
                value={modalForm.commission_fee_policy}
                onValueChange={(v) => setModalForm((f) => ({ ...f, commission_fee_policy: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>
                    {FEE_POLICY_LABELS[modalForm.commission_fee_policy] ?? modalForm.commission_fee_policy}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {FEE_OPTIONS.map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="mt-1 text-xs text-muted-foreground">
                Define quem absorve a taxa do meio de pagamento utilizado.
              </p>
            </div>
          </div>

          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button onClick={handleModalSave} disabled={modalSaving}>
              {modalSaving ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Confirmar exclusão ── */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desativar regra?</DialogTitle>
            <DialogDescription>
              A regra de {deleteTarget ? profName(deleteTarget.professional_id) : ""} deixará de ser aplicada.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Voltar</DialogClose>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Removendo…" : "Desativar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── GlobalForm sub-component ─────────────────────────────────────────────────

function GlobalForm({
  form,
  onChange,
  onSave,
  saving,
  hasExisting,
}: {
  form: FormState
  onChange: (f: FormState) => void
  onSave: () => void
  saving: boolean
  hasExisting: boolean
}) {
  const isCustom = form.commission_base === "CUSTOM_AMOUNT"

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Base de cálculo */}
      <div className="space-y-1.5">
        <Label>Base de cálculo</Label>
        <Select
          value={form.commission_base}
          onValueChange={(v) => onChange({ ...form, commission_base: v ?? "", amount: "" })}
        >
          <SelectTrigger className="w-full">
            <SelectValue>{BASE_LABELS[form.commission_base] ?? form.commission_base}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {BASE_OPTIONS.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Taxa / Valor fixo */}
      <div className="space-y-1.5">
        <Label htmlFor="global-amount">{isCustom ? "Valor fixo (R$)" : "Taxa (%)"}</Label>
        <Input
          id="global-amount"
          type="number"
          step="0.01"
          min="0"
          value={form.amount}
          onChange={(e) => onChange({ ...form, amount: e.target.value })}
          placeholder="0.00"
        />
      </div>

      {/* Quem paga a taxa do gateway */}
      <div className="space-y-1.5">
        <Label>Quem paga a taxa do gateway</Label>
        <Select
          value={form.commission_fee_policy}
          onValueChange={(v) => onChange({ ...form, commission_fee_policy: v ?? "" })}
        >
          <SelectTrigger className="w-full">
            <SelectValue>{FEE_POLICY_LABELS[form.commission_fee_policy] ?? form.commission_fee_policy}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            {FEE_OPTIONS.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="mt-1 text-xs text-muted-foreground">
          Taxa cobrada pelo meio de pagamento (cartão, PIX, etc.)
        </p>
      </div>

      {/* Salvar */}
      <div className="flex items-end">
        <Button onClick={onSave} disabled={saving}>
          {saving ? "Salvando…" : hasExisting ? "Salvar" : "Criar regra global"}
        </Button>
      </div>
    </div>
  )
}
