"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Lock } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatBRL } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CommissionPayoutBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

// ── Types ─────────────────────────────────────────────────────────────────────

interface Commission {
  commission_id: string
  professional_id: string
  commission_amount: string | number
  status: string
  created_at: string
}

interface Professional {
  id: string
  name: string
}

interface CommissionPayout {
  payout_id: string
  professional_id: string
  total_amount: string | number
  status: string
  paid_at: string | null
  created_at: string
}

interface Account {
  account_id: string
  name: string
  is_default_inflow: boolean
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatDT(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  })
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ComissoesPagamentosPage() {
  const { role } = useAuth()

  if (role !== "OWNER" && role !== "ADMIN") {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Comissões" title="Pagamentos de comissões" />
        <EmptyState icon={<Lock size={28} strokeWidth={1.5} />} title="Acesso restrito"
          description="Disponível apenas para Proprietário e Administrador." />
      </div>
    )
  }

  return <PageContent />
}

function PageContent() {
  // ── Bootstrap state ──────────────────────────────────────────────────────────
  const [professionals, setProfessionals] = useState<Professional[]>([])
  const [payouts, setPayouts]             = useState<CommissionPayout[]>([])
  const [accounts, setAccounts]           = useState<Account[]>([])
  const [bootError, setBootError]         = useState<string | null>(null)

  // ── Payout creation state ────────────────────────────────────────────────────
  const [selectedProfId, setSelectedProfId]         = useState<string>("")
  const [pendingCommissions, setPendingCommissions] = useState<Commission[]>([])
  const [pendingLoading, setPendingLoading]         = useState(false)
  const [selectedAccountId, setSelectedAccountId]  = useState<string>("")
  const [posting, setPosting]                       = useState(false)

  // ── Bootstrap fetch ──────────────────────────────────────────────────────────
  const loadBoot = useCallback(async () => {
    setBootError(null)
    try {
      const [profs, pts, accs] = await Promise.all([
        api.get<Professional[]>("/professionals"),
        api.get<CommissionPayout[]>("/commission-payouts"),
        api.get<Account[]>("/financial/accounts"),
      ])
      setProfessionals(profs)
      setPayouts(pts)
      setAccounts(accs)
      const def = accs.find((a) => a.is_default_inflow) ?? accs[0]
      if (def) setSelectedAccountId(def.account_id)
    } catch (e: unknown) {
      setBootError((e as Error).message)
    }
  }, [])

  useEffect(() => { loadBoot() }, [loadBoot])

  // ── Fetch pending commissions when professional changes ──────────────────────
  useEffect(() => {
    if (!selectedProfId) {
      setPendingCommissions([])
      return
    }
    setPendingLoading(true)
    api
      .get<Commission[]>(`/commissions?professional_id=${selectedProfId}`)
      .then((all) =>
        setPendingCommissions(all.filter((c) => c.status === "CALCULATED" || c.status === "DUE")),
      )
      .catch((e: Error) => toast.error(e.message ?? "Erro ao carregar comissões"))
      .finally(() => setPendingLoading(false))
  }, [selectedProfId])

  // ── Reload payouts after successful payout ───────────────────────────────────
  function reloadPayouts() {
    api.get<CommissionPayout[]>("/commission-payouts").then(setPayouts).catch(() => {})
  }

  // ── Submit payout ────────────────────────────────────────────────────────────
  async function handlePayout() {
    if (pendingCommissions.length === 0 || !selectedProfId) return
    setPosting(true)
    try {
      await api.post("/commission-payouts", {
        professional_id: selectedProfId,
        commission_ids: pendingCommissions.map((c) => c.commission_id),
        account_id: selectedAccountId,
      })
      const total = pendingCommissions.reduce((s, c) => s + Number(c.commission_amount), 0)
      toast.success(`Pagamento de ${formatBRL(total)} registrado`)
      reloadPayouts()
      setSelectedProfId("")
      setPendingCommissions([])
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Erro ao registrar pagamento.")
    } finally {
      setPosting(false)
    }
  }

  // ── Derived ──────────────────────────────────────────────────────────────────
  const totalPending = pendingCommissions.reduce((s, c) => s + Number(c.commission_amount), 0)
  const profMap = Object.fromEntries(professionals.map((p) => [p.id, p.name]))

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8">
      <PageHeader
        eyebrow="Comissões"
        title="Pagamentos de comissões"
        description="Registre pagamentos de comissões pendentes e consulte o histórico de payouts."
      />

      {bootError && <ErrorState message={bootError} onRetry={loadBoot} />}

      {/* ── SEÇÃO 1: Criar payout ──────────────────────────────────────────────── */}
      <Card>
        <CardContent className="space-y-5 pt-6">
          <h2 className="text-base font-medium">Registrar pagamento</h2>

          {/* Professional select */}
          <div className="space-y-1.5">
            <Label>Profissional</Label>
            <Select
              value={selectedProfId}
              onValueChange={(v) => setSelectedProfId(v ?? "")}
            >
              <SelectTrigger className="w-full sm:w-72">
                <SelectValue>
                  {selectedProfId
                    ? professionals.find((p) => p.id === selectedProfId)?.name ?? selectedProfId
                    : "Selecione um barbeiro"}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {professionals.map((p) => (
                  <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Pending commissions panel */}
          {selectedProfId && (
            <div className="space-y-4">
              {pendingLoading ? (
                <Skeleton className="h-24 w-full" />
              ) : pendingCommissions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nenhuma comissão pendente para{" "}
                  <span className="font-medium">{profMap[selectedProfId] ?? selectedProfId}</span>.
                </p>
              ) : (
                <>
                  {/* Compact commission list */}
                  <div className="divide-y divide-border rounded-md border border-border">
                    {pendingCommissions.map((c) => (
                      <div key={c.commission_id} className="flex items-center justify-between px-3 py-2 text-sm">
                        <span className="text-muted-foreground">{formatDT(c.created_at)}</span>
                        <span className="font-medium">{formatBRL(Number(c.commission_amount))}</span>
                      </div>
                    ))}
                  </div>

                  <p className="text-sm font-medium">
                    Total a pagar: <span className="text-primary">{formatBRL(totalPending)}</span>
                  </p>

                  {/* Account selector */}
                  {accounts.length > 1 ? (
                    <div className="space-y-1.5">
                      <Label>Conta para débito</Label>
                      <Select value={selectedAccountId} onValueChange={(v) => setSelectedAccountId(v ?? "")}>
                        <SelectTrigger className="w-full sm:w-72">
                          <SelectValue>
                            {accounts.find((a) => a.account_id === selectedAccountId)?.name ?? selectedAccountId}
                          </SelectValue>
                        </SelectTrigger>
                        <SelectContent>
                          {accounts.map((a) => (
                            <SelectItem key={a.account_id} value={a.account_id}>{a.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : accounts.length === 1 ? (
                    <p className="text-sm text-muted-foreground">
                      Conta: <span className="font-medium">{accounts[0].name}</span>
                    </p>
                  ) : null}

                  <Button onClick={handlePayout} disabled={pendingCommissions.length === 0 || posting}>
                    {posting ? "Registrando…" : `Pagar ${formatBRL(totalPending)} em comissões`}
                  </Button>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* ── SEÇÃO 2: Histórico de payouts ─────────────────────────────────────── */}
      <div className="space-y-3">
        <h2 className="text-lg font-medium">Histórico de pagamentos</h2>

        {payouts.length === 0 ? (
          <EmptyState title="Nenhum pagamento" description="Nenhum pagamento de comissão registrado." />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50 text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">Data</th>
                  <th className="px-4 py-3 text-left font-medium">Profissional</th>
                  <th className="px-4 py-3 text-left font-medium">Comissões pagas</th>
                  <th className="px-4 py-3 text-right font-medium">Valor total</th>
                  <th className="px-4 py-3 text-left font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {payouts.map((p) => (
                  <tr key={p.payout_id} className="transition-colors hover:bg-muted/30">
                    <td className="px-4 py-3 text-muted-foreground">{formatDT(p.paid_at ?? p.created_at)}</td>
                    <td className="px-4 py-3 font-medium">{profMap[p.professional_id] ?? p.professional_id}</td>
                    <td className="px-4 py-3 text-muted-foreground">—</td>
                    <td className="px-4 py-3 text-right font-medium">{formatBRL(Number(p.total_amount))}</td>
                    <td className="px-4 py-3"><CommissionPayoutBadge status={p.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
