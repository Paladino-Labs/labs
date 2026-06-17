"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { BadgeDollarSign, ChevronRight, ClipboardList, FileText } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

// ── Types ─────────────────────────────────────────────────────────────────────

interface Commission {
  commission_id: string
  professional_id: string
  commission_amount: number | string
  status: string
  paid_at: string | null
  created_at: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const QUICK_LINKS = [
  {
    href:        "/comissoes/politicas",
    icon:        FileText,
    title:       "Regras",
    description: "Configure regras de comissão por profissional e serviço",
  },
  {
    href:        "/comissoes/historico",
    icon:        ClipboardList,
    title:       "Histórico",
    description: "Visualize comissões geradas por agendamentos",
  },
  {
    href:        "/comissoes/pagamentos",
    icon:        BadgeDollarSign,
    title:       "Pagamentos",
    description: "Pague comissões pendentes e veja histórico de payouts",
  },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function isPending(status: string): boolean {
  return status === "CALCULATED" || status === "DUE"
}

function isWithin30Days(dateStr: string | null): boolean {
  if (!dateStr) return false
  const cutoff = new Date()
  cutoff.setDate(cutoff.getDate() - 30)
  return new Date(dateStr) >= cutoff
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({
  label, value, hint, loading, error,
}: {
  label: string
  value: string
  hint?: string
  loading: boolean
  error: boolean
}) {
  return (
    <Card>
      <CardContent className="p-5">
        <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
        {loading ? (
          <Skeleton className="mt-2 h-9 w-28" />
        ) : (
          <p className="mt-2 font-display text-3xl tracking-tight">
            {error ? <span className="text-destructive text-base">Erro ao carregar</span> : value}
          </p>
        )}
        {hint && <p className="mt-1 text-xs italic text-muted-foreground">{hint}</p>}
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ComissoesPage() {
  const [commissions, setCommissions] = useState<Commission[]>([])
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setCommissions(await api.get<Commission[]>("/commissions"))
    } catch (e: unknown) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // ── KPI derivations ──────────────────────────────────────────────────────────

  const totalPending = useMemo(
    () => commissions
      .filter((c) => isPending(c.status))
      .reduce((s, c) => s + Number(c.commission_amount), 0),
    [commissions],
  )

  const totalPaid30d = useMemo(
    () => commissions
      .filter((c) => c.status === "PAID" && isWithin30Days(c.paid_at))
      .reduce((s, c) => s + Number(c.commission_amount), 0),
    [commissions],
  )

  const pendingProfessionalsCount = useMemo(
    () => new Set(commissions.filter((c) => isPending(c.status)).map((c) => c.professional_id)).size,
    [commissions],
  )

  const hasError = error !== null

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-8">

      <PageHeader
        eyebrow="Financeiro"
        title="Comissões"
        description="Regras, histórico e pagamentos de comissões da equipe."
      />

      {error && !loading && <ErrorState message={error} onRetry={load} />}

      {/* ── KPI Cards ──────────────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard
          label="A pagar"
          value={formatBRL(totalPending)}
          loading={loading}
          error={hasError}
        />
        <KpiCard
          label="Pago (30 dias)"
          value={formatBRL(totalPaid30d)}
          hint="comissões pagas nos últimos 30 dias"
          loading={loading}
          error={hasError}
        />
        <KpiCard
          label="Profissionais com pendência"
          value={String(pendingProfessionalsCount)}
          hint="profissionais com comissões abertas"
          loading={loading}
          error={hasError}
        />
      </div>

      {/* ── Acesso rápido ──────────────────────────────────────────────────────── */}
      <div>
        <h2 className="mb-3 text-xs uppercase tracking-widest text-muted-foreground">
          Acesso rápido
        </h2>
        <div className="grid gap-3 sm:grid-cols-3">
          {QUICK_LINKS.map((s) => (
            <Link key={s.href} href={s.href}>
              <Card className="h-full cursor-pointer transition-colors hover:border-primary">
                <CardContent className="flex items-center gap-3 p-4">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                    <s.icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium leading-tight">{s.title}</p>
                    <p className="mt-0.5 truncate text-xs text-muted-foreground">
                      {s.description}
                    </p>
                  </div>
                  <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>

    </div>
  )
}
