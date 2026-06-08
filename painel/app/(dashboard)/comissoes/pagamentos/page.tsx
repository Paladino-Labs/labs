"use client"

import { useEffect, useState } from "react"
import { CheckCircle } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { formatBRL } from "@/lib/utils"

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
    return <p className="text-sm text-muted-foreground">Acesso restrito.</p>
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
  const [postError, setPostError]                   = useState<string | null>(null)
  const [confirmation, setConfirmation]             = useState<{
    amount: number
    professionalName: string
    count: number
  } | null>(null)

  // ── Bootstrap fetch ──────────────────────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      api.get<Professional[]>("/professionals"),
      api.get<CommissionPayout[]>("/commission-payouts"),
      api.get<Account[]>("/financial/accounts"),
    ])
      .then(([profs, pts, accs]) => {
        setProfessionals(profs)
        setPayouts(pts)
        setAccounts(accs)
        const def = accs.find((a) => a.is_default_inflow) ?? accs[0]
        if (def) setSelectedAccountId(def.account_id)
      })
      .catch((e: Error) => setBootError(e.message))
  }, [])

  // ── Fetch pending commissions when professional changes ──────────────────────
  useEffect(() => {
    if (!selectedProfId) {
      setPendingCommissions([])
      return
    }
    setPendingLoading(true)
    setPostError(null)
    api
      .get<Commission[]>(`/commissions?professional_id=${selectedProfId}`)
      .then((all) =>
        setPendingCommissions(
          all.filter((c) => c.status === "CALCULATED" || c.status === "DUE"),
        ),
      )
      .catch((e: Error) => setPostError(e.message))
      .finally(() => setPendingLoading(false))
  }, [selectedProfId])

  // ── Reload payouts after successful payout ───────────────────────────────────
  function reloadPayouts() {
    api
      .get<CommissionPayout[]>("/commission-payouts")
      .then(setPayouts)
      .catch(() => {})
  }

  // ── Submit payout ────────────────────────────────────────────────────────────
  async function handlePayout() {
    if (pendingCommissions.length === 0 || !selectedProfId) return
    setPosting(true)
    setPostError(null)
    try {
      await api.post("/commission-payouts", {
        professional_id: selectedProfId,
        commission_ids: pendingCommissions.map((c) => c.commission_id),
        account_id: selectedAccountId,
      })
      const prof = professionals.find((p) => p.id === selectedProfId)
      const total = pendingCommissions.reduce(
        (s, c) => s + Number(c.commission_amount),
        0,
      )
      setConfirmation({
        amount: total,
        professionalName: prof?.name ?? selectedProfId,
        count: pendingCommissions.length,
      })
      reloadPayouts()
      // auto-dismiss after 3s
      setTimeout(() => {
        setConfirmation(null)
        setSelectedProfId("")
        setPendingCommissions([])
      }, 3000)
    } catch (e: unknown) {
      setPostError(e instanceof Error ? e.message : "Erro ao registrar pagamento.")
    } finally {
      setPosting(false)
    }
  }

  // ── Derived ──────────────────────────────────────────────────────────────────
  const totalPending = pendingCommissions.reduce(
    (s, c) => s + Number(c.commission_amount),
    0,
  )
  const profMap = Object.fromEntries(professionals.map((p) => [p.id, p.name]))

  // ── Render ───────────────────────────────────────────────────────────────────
  return (
    <div className="space-y-8">

      {/* Cabeçalho */}
      <div>
        <h1 className="font-display text-3xl tracking-wide">Pagamentos de comissões</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Registre pagamentos de comissões pendentes e consulte o histórico de payouts
        </p>
      </div>

      {bootError && (
        <p className="text-sm text-destructive">Não foi possível carregar dados: {bootError}</p>
      )}

      {/* ── SEÇÃO 1: Criar payout ──────────────────────────────────────────────── */}
      <Card>
        <CardContent className="space-y-5 pt-6">
          <h2 className="text-base font-medium">Registrar pagamento</h2>

          {/* Confirmation card */}
          {confirmation && (
            <div className="flex items-start gap-3 rounded-md border border-green-500/30 bg-green-500/10 p-4 text-sm text-green-700 dark:text-green-400">
              <CheckCircle className="mt-0.5 h-4 w-4 shrink-0" />
              <div>
                <p className="font-medium">
                  Pagamento de {formatBRL(confirmation.amount)} registrado com sucesso
                </p>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {confirmation.professionalName} · {confirmation.count}{" "}
                  {confirmation.count === 1 ? "comissão paga" : "comissões pagas"}
                </p>
              </div>
              <button
                className="ml-auto text-muted-foreground hover:text-foreground"
                onClick={() => {
                  setConfirmation(null)
                  setSelectedProfId("")
                  setPendingCommissions([])
                }}
              >
                OK
              </button>
            </div>
          )}

          {/* Professional select */}
          <div className="space-y-1.5">
            <Label>Profissional</Label>
            <Select
              value={selectedProfId}
              onValueChange={(v) => {
                setSelectedProfId(v ?? "")
                setPostError(null)
                setConfirmation(null)
              }}
            >
              <SelectTrigger className="w-full sm:w-72">
                <SelectValue placeholder="Selecione um barbeiro" />
              </SelectTrigger>
              <SelectContent>
                {professionals.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Pending commissions panel */}
          {selectedProfId && !confirmation && (
            <div className="space-y-4">
              {pendingLoading ? (
                <p className="text-sm text-muted-foreground">Carregando comissões…</p>
              ) : pendingCommissions.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Nenhuma comissão pendente para{" "}
                  <span className="font-medium">{profMap[selectedProfId] ?? selectedProfId}</span>.
                </p>
              ) : (
                <>
                  {/* Compact commission list */}
                  <div className="divide-y divide-border rounded-md border">
                    {pendingCommissions.map((c) => (
                      <div
                        key={c.commission_id}
                        className="flex items-center justify-between px-3 py-2 text-sm"
                      >
                        <span className="text-muted-foreground">
                          {formatDT(c.created_at)}
                        </span>
                        <span className="font-medium">
                          {formatBRL(Number(c.commission_amount))}
                        </span>
                      </div>
                    ))}
                  </div>

                  <p className="text-sm font-medium">
                    Total a pagar:{" "}
                    <span className="text-primary">{formatBRL(totalPending)}</span>
                  </p>

                  {/* Account selector */}
                  {accounts.length > 1 ? (
                    <div className="space-y-1.5">
                      <Label>Conta para débito</Label>
                      <Select
                        value={selectedAccountId}
                        onValueChange={(v) => setSelectedAccountId(v ?? "")}
                      >
                        <SelectTrigger className="w-full sm:w-72">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {accounts.map((a) => (
                            <SelectItem key={a.account_id} value={a.account_id}>
                              {a.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                  ) : accounts.length === 1 ? (
                    <p className="text-sm text-muted-foreground">
                      Conta: <span className="font-medium">{accounts[0].name}</span>
                    </p>
                  ) : null}

                  {postError && (
                    <p className="text-sm text-destructive">{postError}</p>
                  )}

                  <Button
                    onClick={handlePayout}
                    disabled={pendingCommissions.length === 0 || posting}
                  >
                    {posting
                      ? "Registrando…"
                      : `Pagar ${formatBRL(totalPending)} em comissões`}
                  </Button>
                </>
              )}
            </div>
          )}

          {postError && !selectedProfId && (
            <p className="text-sm text-destructive">{postError}</p>
          )}
        </CardContent>
      </Card>

      {/* ── SEÇÃO 2: Histórico de payouts ─────────────────────────────────────── */}
      <div className="space-y-3">
        <h2 className="text-lg font-medium">Histórico de pagamentos</h2>

        {payouts.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Nenhum pagamento de comissão registrado.
          </p>
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <th className="px-4 py-2.5 text-left font-medium">Data</th>
                  <th className="px-4 py-2.5 text-left font-medium">Profissional</th>
                  <th className="px-4 py-2.5 text-left font-medium">Comissões pagas</th>
                  <th className="px-4 py-2.5 text-right font-medium">Valor total</th>
                  <th className="px-4 py-2.5 text-left font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {payouts.map((p) => (
                  <tr key={p.payout_id} className="hover:bg-muted/20">
                    <td className="px-4 py-3 text-muted-foreground">
                      {formatDT(p.paid_at ?? p.created_at)}
                    </td>
                    <td className="px-4 py-3 font-medium">
                      {profMap[p.professional_id] ?? p.professional_id}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">—</td>
                    <td className="px-4 py-3 text-right font-medium">
                      {formatBRL(Number(p.total_amount))}
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant="default" className="bg-green-600 text-white hover:bg-green-600">
                        Pago
                      </Badge>
                    </td>
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
