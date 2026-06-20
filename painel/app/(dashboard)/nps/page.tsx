"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Eye } from "lucide-react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { NPS_SURVEY_STATUS_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { NpsSurveyBadge, NpsScoreChip } from "@/components/FsmBadge"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"

interface NpsResponse {
  id: string
  survey_id: string
  score: number
  comment?: string | null
  tenant_response?: string | null
  responded_at?: string | null
}

interface NpsSurvey {
  id: string
  company_id: string
  customer_id: string
  appointment_id: string
  status: string
  scheduled_for: string
  sent_at?: string | null
  responded_at?: string | null
  expires_at: string
  response?: NpsResponse | null
}

interface Customer {
  id: string
  name?: string | null
}

const STATUS_FILTER: Record<string, string> = {
  all: "Todos",
  PENDING: "Pendente", SENT: "Enviada", RESPONDED: "Respondida", EXPIRED: "Expirada",
}

export default function NpsSurveysPage() {
  const [surveys, setSurveys] = useState<NpsSurvey[]>([])
  const [customers, setCustomers] = useState<Map<string, string>>(new Map())
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [statusFilter, setStatusFilter] = useState("all")
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [detail, setDetail] = useState<NpsSurvey | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [reply, setReply] = useState("")
  const [replying, setReplying] = useState(false)

  useEffect(() => {
    api.get<Customer[]>("/customers/")
      .then((list) => setCustomers(new Map(list.map((c) => [c.id, c.name ?? ""]))))
      .catch(() => {})
  }, [])

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    const params = new URLSearchParams()
    if (statusFilter !== "all") params.set("status", statusFilter)
    if (dateFrom) params.set("date_from", dateFrom)
    if (dateTo) params.set("date_to", dateTo)
    const q = params.toString()
    try {
      setSurveys(await api.get<NpsSurvey[]>(`/nps/surveys${q ? `?${q}` : ""}`))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [statusFilter, dateFrom, dateTo])

  useEffect(() => { load() }, [load])

  const customerName = useMemo(
    () => (id: string) => customers.get(id) || "Em breve",
    [customers],
  )

  async function openDetail(id: string) {
    setDetailLoading(true)
    setReply("")
    try {
      const d = await api.get<NpsSurvey>(`/nps/surveys/${id}`)
      setDetail(d)
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao carregar detalhe")
    } finally {
      setDetailLoading(false)
    }
  }

  async function handleReply() {
    if (!detail || !reply.trim()) return
    setReplying(true)
    try {
      const updated = await api.post<NpsResponse>(`/nps/surveys/${detail.id}/respond`, {
        response: reply.trim(),
      })
      toast.success("Resposta enviada ao cliente")
      setDetail({ ...detail, response: { ...(detail.response as NpsResponse), ...updated } })
      setReply("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao responder")
    } finally {
      setReplying(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="NPS" title="Pesquisas" description="Acompanhe envios, respostas e notas de satisfação.">
        <Button variant="outline" render={<Link href="/nps/config" />}>Configuração</Button>
      </PageHeader>

      {/* Filtros */}
      <div className="grid gap-4 sm:grid-cols-3 lg:max-w-2xl">
        <div className="space-y-1">
          <Label>Status</Label>
          <Select value={statusFilter} onValueChange={(v) => v && setStatusFilter(v)}>
            <SelectTrigger className="w-full"><SelectValue>{STATUS_FILTER[statusFilter]}</SelectValue></SelectTrigger>
            <SelectContent>
              {Object.entries(STATUS_FILTER).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="nps-from">De</Label>
          <Input id="nps-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="nps-to">Até</Label>
          <Input id="nps-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
      </div>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : surveys.length === 0 ? (
        <EmptyState
          title="Nenhuma pesquisa ainda"
          description="As pesquisas de NPS são enviadas automaticamente após cada atendimento concluído — você não precisa criá-las manualmente. Assim que houver envios, eles aparecem aqui. Ajuste a cadência e os gatilhos em NPS › Configuração."
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-muted-foreground">
              <tr>
                <th className="px-4 py-3 text-left font-medium">Cliente</th>
                <th className="px-4 py-3 text-left font-medium">Status</th>
                <th className="px-4 py-3 text-left font-medium">Agendada</th>
                <th className="px-4 py-3 text-left font-medium">Enviada</th>
                <th className="px-4 py-3 text-left font-medium">Respondida</th>
                <th className="px-4 py-3 text-left font-medium">Nota</th>
                <th className="px-4 py-3 text-right font-medium">Ações</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {surveys.map((s) => (
                <tr key={s.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium">{customerName(s.customer_id)}</td>
                  <td className="px-4 py-3"><NpsSurveyBadge status={s.status} /></td>
                  <td className="px-4 py-3 text-muted-foreground">{formatDateTime(s.scheduled_for)}</td>
                  <td className="px-4 py-3 text-muted-foreground">{s.sent_at ? formatDateTime(s.sent_at) : "—"}</td>
                  <td className="px-4 py-3 text-muted-foreground">{s.responded_at ? formatDateTime(s.responded_at) : "—"}</td>
                  <td className="px-4 py-3"><NpsScoreChip score={s.response?.score} /></td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end">
                      <Button size="icon-sm" variant="ghost" onClick={() => openDetail(s.id)} aria-label="Ver detalhe">
                        <Eye className="h-4 w-4" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detalhe */}
      <Sheet open={!!detail || detailLoading} onOpenChange={(v) => { if (!v) setDetail(null) }}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>Pesquisa NPS</SheetTitle>
            <SheetDescription>
              {detail ? customerName(detail.customer_id) : "Carregando…"}
            </SheetDescription>
          </SheetHeader>

          {detailLoading && !detail ? (
            <Skeleton className="h-40 w-full" />
          ) : detail ? (
            <div className="space-y-5 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Status"><NpsSurveyBadge status={detail.status} /></Field>
                <Field label="Agendada">{formatDateTime(detail.scheduled_for)}</Field>
                <Field label="Enviada">{detail.sent_at ? formatDateTime(detail.sent_at) : "—"}</Field>
                <Field label="Expira">{formatDateTime(detail.expires_at)}</Field>
              </div>

              {/* Resposta do cliente */}
              <div className="rounded-lg border border-border p-4">
                <p className="label-eyebrow mb-2">Resposta do cliente</p>
                {detail.response ? (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2">
                      <NpsScoreChip score={detail.response.score} />
                      <span className="text-muted-foreground">Nota atribuída pelo cliente</span>
                    </div>
                    <p className="text-foreground">
                      {detail.response.comment || <span className="text-muted-foreground italic">Sem comentário.</span>}
                    </p>
                  </div>
                ) : (
                  <p className="text-muted-foreground">Cliente ainda não respondeu.</p>
                )}
              </div>

              {/* Réplica do tenant */}
              {detail.response && (
                <div className="rounded-lg border border-border p-4">
                  <p className="label-eyebrow mb-2">Réplica da empresa</p>
                  {detail.response.tenant_response ? (
                    <p className="text-foreground whitespace-pre-wrap">{detail.response.tenant_response}</p>
                  ) : detail.status === "RESPONDED" ? (
                    <div className="space-y-2">
                      <Textarea
                        value={reply}
                        onChange={(e) => setReply(e.target.value)}
                        maxLength={2000}
                        rows={4}
                        placeholder="Escreva uma resposta ao cliente (não altera a nota)…"
                      />
                      <div className="flex justify-end">
                        <Button onClick={handleReply} disabled={replying || !reply.trim()}>
                          {replying ? "Enviando…" : "Responder"}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <p className="text-muted-foreground">Disponível após o cliente responder.</p>
                  )}
                </div>
              )}
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs text-muted-foreground">{label}</p>
      <div>{children}</div>
    </div>
  )
}
