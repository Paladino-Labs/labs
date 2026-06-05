"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Lock } from "lucide-react"

interface FeePolicy {
  fee_source: string
  fee_percentage: number | null
  fee_flat: number
  is_active: boolean
}

const FEE_SOURCE_LABELS: Record<string, string> = {
  CASH:              "Dinheiro",
  PIX:               "PIX online (Asaas)",
  MAQUININHA_PIX:    "PIX na maquininha",
  MAQUININHA_CREDIT: "Cartão de crédito",
  MAQUININHA_DEBIT:  "Cartão de débito",
  CARD_CREDIT:       "Crédito online",
  CARD_DEBIT:        "Débito online",
  BOLETO:            "Boleto",
}

const EDITABLE_SOURCES = new Set([
  "PIX", "MAQUININHA_PIX", "MAQUININHA_CREDIT", "MAQUININHA_DEBIT",
  "CARD_CREDIT", "CARD_DEBIT", "BOLETO",
])

function AccessRestricted() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center text-muted-foreground">
      <Lock className="h-8 w-8 opacity-40" />
      <p className="text-base font-medium">Acesso restrito</p>
      <p className="text-sm">Esta página está disponível apenas para OWNER e ADMIN.</p>
    </div>
  )
}

export default function TaxasPage() {
  const { role, hydrated } = useAuth()
  const [policies, setPolicies] = useState<FeePolicy[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Per-row editable state: fee_percentage and fee_flat
  const [edits, setEdits] = useState<Record<string, { pct: string; flat: string }>>({})
  // Per-row save feedback: "saving" | "saved" | "error:<msg>" | null
  const [feedback, setFeedback] = useState<Record<string, string | null>>({})

  const canAccess = role === "OWNER" || role === "ADMIN"

  useEffect(() => {
    if (!hydrated) return
    if (!canAccess) return
    api
      .get<FeePolicy[]>("/financial/fee-policies")
      .then((data) => {
        setPolicies(data)
        const initial: Record<string, { pct: string; flat: string }> = {}
        for (const p of data) {
          initial[p.fee_source] = {
            pct:  p.fee_percentage != null ? String(p.fee_percentage) : "",
            flat: String(p.fee_flat),
          }
        }
        setEdits(initial)
      })
      .catch((e: unknown) => setError((e as Error).message ?? "Erro ao carregar taxas"))
      .finally(() => setLoading(false))
  }, [canAccess, hydrated])

  if (!canAccess) return <AccessRestricted />
  if (loading) return <p className="text-muted-foreground">Carregando…</p>
  if (error)   return <p className="text-destructive">{error}</p>

  async function handleSave(source: string) {
    const edit = edits[source]
    if (!edit) return

    setFeedback((f) => ({ ...f, [source]: "saving" }))
    try {
      await api.patch<FeePolicy>(`/financial/fee-policies/${source}`, {
        fee_percentage: edit.pct !== "" ? parseFloat(edit.pct) : null,
        fee_flat: parseFloat(edit.flat) || 0,
      })
      setFeedback((f) => ({ ...f, [source]: "saved" }))
      setTimeout(() => setFeedback((f) => ({ ...f, [source]: null })), 2000)
    } catch (e: unknown) {
      setFeedback((f) => ({ ...f, [source]: `error:${(e as Error).message ?? "Erro"}` }))
    }
  }

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="[font-family:var(--font-display)] text-3xl tracking-wide">Taxas de maquininha</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Configure as taxas de processamento por método de pagamento.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Métodos de pagamento</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs text-muted-foreground">
                  <th className="px-6 py-3 font-medium">Método</th>
                  <th className="px-4 py-3 font-medium">Taxa (%)</th>
                  <th className="px-4 py-3 font-medium">Fixa (R$)</th>
                  <th className="px-4 py-3 font-medium">Ações</th>
                </tr>
              </thead>
              <tbody>
                {policies.map((policy) => {
                  const label    = FEE_SOURCE_LABELS[policy.fee_source] ?? policy.fee_source
                  const editable = EDITABLE_SOURCES.has(policy.fee_source)
                  const edit     = edits[policy.fee_source] ?? { pct: "", flat: "0" }
                  const fb       = feedback[policy.fee_source]
                  const saving   = fb === "saving"
                  const saved    = fb === "saved"
                  const errMsg   = fb?.startsWith("error:") ? fb.slice(6) : null

                  return (
                    <tr key={policy.fee_source} className="border-b last:border-0">
                      <td className="px-6 py-3 font-medium">{label}</td>

                      {/* Taxa % */}
                      <td className="px-4 py-3">
                        {!editable ? (
                          <span className="text-muted-foreground">0% <span className="text-xs">(sem taxa)</span></span>
                        ) : policy.fee_percentage === null ? (
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              step="0.01"
                              min="0"
                              max="100"
                              value={edit.pct}
                              onChange={(e) =>
                                setEdits((prev) => ({ ...prev, [policy.fee_source]: { ...edit, pct: e.target.value } }))
                              }
                              placeholder="—"
                              className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                            />
                            <span className="text-xs text-amber-600">Não configurado</span>
                          </div>
                        ) : (
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            max="100"
                            value={edit.pct}
                            onChange={(e) =>
                              setEdits((prev) => ({ ...prev, [policy.fee_source]: { ...edit, pct: e.target.value } }))
                            }
                            className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          />
                        )}
                      </td>

                      {/* Fixa R$ */}
                      <td className="px-4 py-3">
                        {!editable ? (
                          <span className="text-muted-foreground">R$ 0,00</span>
                        ) : (
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={edit.flat}
                            onChange={(e) =>
                              setEdits((prev) => ({ ...prev, [policy.fee_source]: { ...edit, flat: e.target.value } }))
                            }
                            className="w-24 rounded-md border border-input bg-background px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
                          />
                        )}
                      </td>

                      {/* Ações */}
                      <td className="px-4 py-3">
                        {editable ? (
                          <div className="flex items-center gap-2">
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleSave(policy.fee_source)}
                              disabled={saving}
                            >
                              {saving ? "Salvando…" : "Salvar"}
                            </Button>
                            {saved && (
                              <span className="text-xs text-green-600">Salvo ✓</span>
                            )}
                            {errMsg && (
                              <span className="text-xs text-destructive">{errMsg}</span>
                            )}
                          </div>
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
    </div>
  )
}
