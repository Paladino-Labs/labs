"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { formatBRL } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
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
  SelectValue,
} from "@/components/ui/select"
import { PencilIcon, Trash2Icon, PlusIcon } from "lucide-react"

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
  const [globalForm,     setGlobalForm]     = useState<FormState>(EMPTY_FORM)
  const [globalFeedback, setGlobalFeedback] = useState<string | null>(null)
  const [globalSaving,   setGlobalSaving]   = useState(false)

  // Modal
  const [modalOpen,    setModalOpen]    = useState(false)
  const [editingPolicy, setEditingPolicy] = useState<CommissionPolicyResponse | null>(null)
  const [modalForm,    setModalForm]    = useState<FormState>(EMPTY_FORM)
  const [modalSaving,  setModalSaving]  = useState(false)
  const [modalError,   setModalError]   = useState<string | null>(null)

  // Confirm delete
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  const canAccess = role === "OWNER" || role === "ADMIN"

  async function loadAll() {
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
  }

  useEffect(() => {
    if (!hydrated) return
    if (!canAccess) return
    loadAll()
  }, [canAccess, hydrated]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!hydrated) return null
  if (!canAccess)
    return <p className="text-sm text-muted-foreground">Acesso restrito.</p>
  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error)   return <p className="text-destructive">{error}</p>

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
    setGlobalFeedback(null)
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
        await api.post("/commission-policies", {
          ...body,
          professional_id: null,
          service_id:      null,
        })
      }
      setGlobalFeedback("saved")
      setTimeout(() => setGlobalFeedback(null), 2000)
      await loadAll()
    } catch (e: unknown) {
      setGlobalFeedback(`error:${(e as Error).message ?? "Erro"}`)
    } finally {
      setGlobalSaving(false)
    }
  }

  // ── Modal helpers ────────────────────────────────────────────────────────────

  function openCreate() {
    setEditingPolicy(null)
    setModalForm(EMPTY_FORM)
    setModalError(null)
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
    setModalError(null)
    setModalOpen(true)
  }

  async function handleModalSave() {
    setModalSaving(true)
    setModalError(null)
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
      setModalOpen(false)
      await loadAll()
    } catch (e: unknown) {
      setModalError((e as Error).message ?? "Erro ao salvar")
    } finally {
      setModalSaving(false)
    }
  }

  // ── Delete ──────────────────────────────────────────────────────────────────

  async function handleDelete(policy_id: string) {
    try {
      await api.delete(`/commission-policies/${policy_id}`)
      setConfirmDeleteId(null)
      await loadAll()
    } catch (e: unknown) {
      alert((e as Error).message ?? "Erro ao excluir")
    }
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="max-w-4xl space-y-8">

      {/* Page header */}
      <div>
        <h1 className="text-3xl tracking-wide">Regras de comissão</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure como as comissões são calculadas para cada barbeiro e serviço.
        </p>
      </div>

      {/* ── Seção 1: Política global ── */}
      <Card>
        <CardHeader>
          <CardTitle>Regra global</CardTitle>
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
            feedback={globalFeedback}
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
        <CardContent className="p-0">
          {specificActive.length === 0 ? (
            <p className="px-6 py-8 text-center text-sm text-muted-foreground">
              Nenhuma regra específica cadastrada.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-xs text-muted-foreground">
                    <th className="px-6 py-3 font-medium">Profissional</th>
                    <th className="px-4 py-3 font-medium">Serviço</th>
                    <th className="px-4 py-3 font-medium">Base</th>
                    <th className="px-4 py-3 font-medium">Taxa</th>
                    <th className="px-4 py-3 font-medium">Quando</th>
                    <th className="px-4 py-3 font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {specificActive.map((policy) => (
                    <tr key={policy.policy_id} className="border-b last:border-0">
                      <td className="px-6 py-3">{profName(policy.professional_id)}</td>
                      <td className="px-4 py-3">{svcName(policy.service_id)}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {BASE_LABELS[policy.commission_base] ?? policy.commission_base}
                      </td>
                      <td className="px-4 py-3 font-medium">{formatRate(policy)}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {FEE_POLICY_LABELS[policy.commission_fee_policy] ?? policy.commission_fee_policy}
                      </td>
                      <td className="px-4 py-3">
                        {confirmDeleteId === policy.policy_id ? (
                          <div className="flex items-center gap-2">
                            <span className="text-xs text-muted-foreground">Desativar?</span>
                            <Button
                              size="sm"
                              variant="destructive"
                              onClick={() => handleDelete(policy.policy_id)}
                            >
                              Sim
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setConfirmDeleteId(null)}
                            >
                              Não
                            </Button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1">
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              onClick={() => openEdit(policy)}
                              aria-label="Editar"
                            >
                              <PencilIcon className="size-4" />
                            </Button>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              className="text-destructive hover:text-destructive"
                              onClick={() => setConfirmDeleteId(policy.policy_id)}
                              aria-label="Excluir"
                            >
                              <Trash2Icon className="size-4" />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── Modal criação/edição ── */}
      <Dialog open={modalOpen} onOpenChange={setModalOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {editingPolicy ? "Editar regra" : "Nova regra específica"}
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Profissional */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Profissional</label>
              <Select
                value={modalForm.professional_id}
                onValueChange={(v) => setModalForm((f) => ({ ...f, professional_id: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Todos os barbeiros" />
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
              <label className="text-xs font-medium text-muted-foreground">Serviço</label>
              <Select
                value={modalForm.service_id}
                onValueChange={(v) => setModalForm((f) => ({ ...f, service_id: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Todos os serviços" />
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
              <label className="text-xs font-medium text-muted-foreground">Base de cálculo</label>
              <Select
                value={modalForm.commission_base}
                onValueChange={(v) =>
                  setModalForm((f) => ({ ...f, commission_base: v ?? "", amount: "" }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
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
              <label className="text-xs font-medium text-muted-foreground">
                {modalForm.commission_base === "CUSTOM_AMOUNT" ? "Valor fixo (R$)" : "Taxa (%)"}
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={modalForm.amount}
                onChange={(e) => setModalForm((f) => ({ ...f, amount: e.target.value }))}
                placeholder="0.00"
                className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
            </div>

            {/* Quem paga a taxa do gateway */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Quem paga a taxa do gateway</label>
              <Select
                value={modalForm.commission_fee_policy}
                onValueChange={(v) => setModalForm((f) => ({ ...f, commission_fee_policy: v ?? "" }))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FEE_OPTIONS.map(([value, label]) => (
                    <SelectItem key={value} value={value}>{label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground mt-1">
                Taxa cobrada pelo meio de pagamento (cartão, PIX, etc.)
              </p>
            </div>

            {modalError && (
              <p className="text-xs text-destructive">{modalError}</p>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModalOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleModalSave} disabled={modalSaving}>
              {modalSaving ? "Salvando…" : "Salvar"}
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
  feedback,
  hasExisting,
}: {
  form: FormState
  onChange: (f: FormState) => void
  onSave: () => void
  saving: boolean
  feedback: string | null
  hasExisting: boolean
}) {
  const isCustom = form.commission_base === "CUSTOM_AMOUNT"
  const saved    = feedback === "saved"
  const errMsg   = feedback?.startsWith("error:") ? feedback.slice(6) : null

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {/* Base de cálculo */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Base de cálculo</label>
        <Select
          value={form.commission_base}
          onValueChange={(v) => onChange({ ...form, commission_base: v ?? "", amount: "" })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
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
        <label className="text-xs font-medium text-muted-foreground">
          {isCustom ? "Valor fixo (R$)" : "Taxa (%)"}
        </label>
        <input
          type="number"
          step="0.01"
          min="0"
          value={form.amount}
          onChange={(e) => onChange({ ...form, amount: e.target.value })}
          placeholder="0.00"
          className="h-8 w-full rounded-lg border border-input bg-background px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
      </div>

      {/* Quem paga a taxa do gateway */}
      <div className="space-y-1.5">
        <label className="text-xs font-medium text-muted-foreground">Quem paga a taxa do gateway</label>
        <Select
          value={form.commission_fee_policy}
          onValueChange={(v) => onChange({ ...form, commission_fee_policy: v ?? "" })}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {FEE_OPTIONS.map(([value, label]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-muted-foreground mt-1">
          Taxa cobrada pelo meio de pagamento (cartão, PIX, etc.)
        </p>
      </div>

      {/* Salvar */}
      <div className="flex items-end gap-2">
        <Button onClick={onSave} disabled={saving} size="sm" className="h-8">
          {saving ? "Salvando…" : hasExisting ? "Salvar" : "Criar regra global"}
        </Button>
        {saved && (
          <span className="text-xs text-green-600">Salvo ✓</span>
        )}
        {errMsg && (
          <span className="text-xs text-destructive">{errMsg}</span>
        )}
      </div>
    </div>
  )
}
