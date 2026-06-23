"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { Lock } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/context/AuthContext"
import { formatBRL } from "@/lib/utils"
import type { Commission } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { CommissionBadge } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

const OPERATION_TYPE_LABELS: Record<string, string> = {
  SERVICE_RENDERED: "Agendamento",
  PACKAGE_SOLD:     "Venda de pacote",
  SUBSCRIPTION:     "Assinatura",
  APPOINTMENT:      "Agendamento",
  PACKAGE:          "Pacote",
}

function formatDT(iso: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  })
}

function isPending(status: string): boolean {
  return status === "CALCULATED" || status === "DUE"
}

export default function MinhasComissoesPage() {
  const router = useRouter()
  const { role, hydrated } = useAuth()

  // Guard: exclusivo do PROFESSIONAL.
  useEffect(() => {
    if (hydrated && role !== "PROFESSIONAL") router.replace("/")
  }, [hydrated, role, router])

  const [commissions, setCommissions] = useState<Commission[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const fetchCommissions = useCallback(() => {
    setLoading(true)
    setError(null)
    const params = new URLSearchParams()
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    const qs = params.toString()
    api
      .get<Commission[]>(`/commissions/me${qs ? `?${qs}` : ""}`)
      .then(setCommissions)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [dateFrom, dateTo])

  useEffect(() => {
    if (!hydrated || role !== "PROFESSIONAL") return
    fetchCommissions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hydrated, role])

  // Agrupamento para a aba Pagamentos.
  const grupos = useMemo(() => {
    const aReceber = commissions.filter((c) => isPending(c.status))
    const recebido = commissions.filter((c) => c.status === "PAID")
    const sum = (list: Commission[]) =>
      list.reduce((s, c) => s + Number(c.commission_amount ?? 0), 0)
    return {
      aReceber,
      recebido,
      totalAReceber: sum(aReceber),
      totalRecebido: sum(recebido),
    }
  }, [commissions])

  if (!hydrated) return null
  if (role !== "PROFESSIONAL") {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Comissões" title="Minhas comissões" />
        <EmptyState icon={<Lock size={28} strokeWidth={1.5} />} title="Acesso restrito"
          description="Disponível apenas para profissionais." />
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Comissões"
        title="Minhas comissões"
        description="Comissões geradas pelos seus atendimentos, vendas de pacotes e assinaturas."
      />

      {/* Filtros de período */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base font-medium">Período</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4">
          <div className="space-y-1">
            <Label htmlFor="mc-from">De</Label>
            <Input id="mc-from" type="date" value={dateFrom}
              onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="mc-to">Até</Label>
            <Input id="mc-to" type="date" value={dateTo}
              onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          <Button onClick={fetchCommissions}>Filtrar</Button>
        </CardContent>
      </Card>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={fetchCommissions} />
      ) : (
        <Tabs defaultValue="historico">
          <TabsList>
            <TabsTrigger value="historico">Histórico</TabsTrigger>
            <TabsTrigger value="pagamentos">Pagamentos</TabsTrigger>
          </TabsList>

          {/* ── Histórico ─────────────────────────────────────────────────── */}
          <TabsContent value="historico">
            {commissions.length === 0 ? (
              <EmptyState title="Nenhuma comissão"
                description="Nenhuma comissão encontrada para o período selecionado." />
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead className="bg-muted/50 text-muted-foreground">
                    <tr>
                      <th className="px-4 py-3 text-left font-medium">Data</th>
                      <th className="px-4 py-3 text-left font-medium">Tipo</th>
                      <th className="px-4 py-3 text-right font-medium">Valor bruto</th>
                      <th className="px-4 py-3 text-right font-medium">Comissão</th>
                      <th className="px-4 py-3 text-left font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {commissions.map((c) => (
                      <tr key={c.commission_id} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 text-muted-foreground">{formatDT(c.created_at)}</td>
                        <td className="px-4 py-3">
                          {OPERATION_TYPE_LABELS[c.operation_type] ?? c.operation_type}
                        </td>
                        <td className="px-4 py-3 text-right">{formatBRL(Number(c.gross_amount))}</td>
                        <td className="px-4 py-3 text-right font-medium">
                          {formatBRL(Number(c.commission_amount))}
                        </td>
                        <td className="px-4 py-3"><CommissionBadge status={c.status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          {/* ── Pagamentos ────────────────────────────────────────────────── */}
          <TabsContent value="pagamentos">
            <div className="grid gap-4 sm:grid-cols-2">
              <GrupoCard
                title="A receber"
                total={grupos.totalAReceber}
                items={grupos.aReceber}
                emptyLabel="Nenhuma comissão a receber."
              />
              <GrupoCard
                title="Recebido"
                total={grupos.totalRecebido}
                items={grupos.recebido}
                emptyLabel="Nenhuma comissão recebida."
              />
            </div>
          </TabsContent>
        </Tabs>
      )}
    </div>
  )
}

function GrupoCard({
  title,
  total,
  items,
  emptyLabel,
}: {
  title: string
  total: number
  items: Commission[]
  emptyLabel: string
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base font-medium">{title}</CardTitle>
          <span className="font-display text-2xl">{formatBRL(total)}</span>
        </div>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyLabel}</p>
        ) : (
          <ul className="divide-y divide-border -my-1">
            {items.map((c) => (
              <li key={c.commission_id} className="flex items-center justify-between py-2.5 text-sm">
                <span className="text-muted-foreground">{formatDT(c.created_at)}</span>
                <span className="flex items-center gap-3">
                  <CommissionBadge status={c.status} />
                  <span className="font-medium">{formatBRL(Number(c.commission_amount))}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}
