"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Lock } from "lucide-react"
import { api } from "@/lib/api"
import { FEE_SOURCE_LABELS } from "@/lib/constants"
import { useAuth } from "@/hooks/useAuth"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"

interface FeePolicy {
  fee_source: string
  fee_percentage: number | null
  fee_flat: number
  is_active: boolean
}

// Todos os fee_sources são editáveis, exceto CASH (sempre sem taxa)
const EDITABLE_SOURCES = new Set(
  Object.keys(FEE_SOURCE_LABELS).filter((s) => s !== "CASH")
)

export default function TaxasPage() {
  const { role, hydrated } = useAuth()
  const [policies, setPolicies] = useState<FeePolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Per-row editable state: fee_percentage and fee_flat
  const [edits, setEdits] = useState<Record<string, { pct: string; flat: string }>>({})
  // Per-row saving flag
  const [saving, setSaving] = useState<Record<string, boolean>>({})

  const canEdit = role === "OWNER" || role === "ADMIN"
  // PROFESSIONAL tem acesso somente leitura (Passo 10). ⚠ Depende de o backend
  // permitir GET /financial/fee-policies para PROFESSIONAL (hoje OWNER/ADMIN-only).
  const canAccess = canEdit || role === "PROFESSIONAL"

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const data = await api.get<FeePolicy[]>("/financial/fee-policies")
      setPolicies(data)
      const initial: Record<string, { pct: string; flat: string }> = {}
      for (const p of data) {
        initial[p.fee_source] = {
          pct:  p.fee_percentage != null ? String(p.fee_percentage) : "",
          flat: String(p.fee_flat),
        }
      }
      setEdits(initial)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao carregar taxas")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!hydrated || !canAccess) return
    load()
  }, [canAccess, hydrated, load])

  async function handleSave(source: string) {
    const edit = edits[source]
    if (!edit) return
    setSaving((s) => ({ ...s, [source]: true }))
    try {
      await api.patch<FeePolicy>(`/financial/fee-policies/${source}`, {
        fee_percentage: edit.pct !== "" ? parseFloat(edit.pct) : null,
        fee_flat: parseFloat(edit.flat) || 0,
      })
      toast.success(`Taxa de ${FEE_SOURCE_LABELS[source] ?? source} salva`)
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving((s) => ({ ...s, [source]: false }))
    }
  }

  if (!hydrated) return null

  if (!canAccess) {
    return (
      <div className="space-y-6">
        <PageHeader eyebrow="Configurações" title="Taxas de maquininha" />
        <EmptyState icon={<Lock size={28} strokeWidth={1.5} />} title="Acesso restrito"
          description="Disponível apenas para Proprietário e Administrador." />
      </div>
    )
  }

  return (
    <div className="max-w-3xl space-y-6">
      <PageHeader
        eyebrow="Configurações"
        title="Taxas de maquininha"
        description="Configure as taxas de processamento por método de pagamento."
      />

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Métodos de pagamento</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead className="bg-muted/50 text-muted-foreground">
                  <tr>
                    <th className="px-4 py-3 text-left font-medium">Método</th>
                    <th className="px-4 py-3 text-left font-medium">Taxa (%)</th>
                    <th className="px-4 py-3 text-left font-medium">Fixa (R$)</th>
                    <th className="px-4 py-3 text-right font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {policies.map((policy) => {
                    const label    = FEE_SOURCE_LABELS[policy.fee_source] ?? policy.fee_source
                    const editable = EDITABLE_SOURCES.has(policy.fee_source)
                    const edit     = edits[policy.fee_source] ?? { pct: "", flat: "0" }
                    const isSaving = !!saving[policy.fee_source]
                    const notConfigured = editable && policy.fee_percentage === null

                    return (
                      <tr key={policy.fee_source} className="transition-colors hover:bg-muted/30">
                        <td className="px-4 py-3 font-medium">{label}</td>

                        {/* Taxa % */}
                        <td className="px-4 py-3">
                          {!editable ? (
                            <span className="text-muted-foreground">0% <span className="text-xs">— sem taxa</span></span>
                          ) : !canEdit ? (
                            <span>{policy.fee_percentage != null ? `${policy.fee_percentage}%` : "—"}</span>
                          ) : (
                            <div className="flex items-center gap-2">
                              <Input
                                type="number" step="0.01" min="0" max="100"
                                value={edit.pct}
                                onChange={(e) =>
                                  setEdits((prev) => ({ ...prev, [policy.fee_source]: { ...edit, pct: e.target.value } }))
                                }
                                placeholder="—"
                                className="w-24"
                              />
                              {notConfigured && <span className="text-xs text-muted-foreground">Não configurado</span>}
                            </div>
                          )}
                        </td>

                        {/* Fixa R$ */}
                        <td className="px-4 py-3">
                          {!editable ? (
                            <span className="text-muted-foreground">—</span>
                          ) : !canEdit ? (
                            <span>R$ {Number(policy.fee_flat ?? 0).toFixed(2)}</span>
                          ) : (
                            <Input
                              type="number" step="0.01" min="0"
                              value={edit.flat}
                              onChange={(e) =>
                                setEdits((prev) => ({ ...prev, [policy.fee_source]: { ...edit, flat: e.target.value } }))
                              }
                              className="w-24"
                            />
                          )}
                        </td>

                        {/* Ações */}
                        <td className="px-4 py-3 text-right">
                          {editable && canEdit ? (
                            <Button size="sm" variant="outline" onClick={() => handleSave(policy.fee_source)} disabled={isSaving}>
                              {isSaving ? "Salvando…" : "Salvar"}
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
