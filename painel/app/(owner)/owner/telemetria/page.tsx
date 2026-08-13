"use client"

/**
 * Telemetria do bot — lista de conversas (S-painel-telemetria).
 *
 * A tela principal do painel de plataforma. O Silva lê as conversas dos dias
 * de coleta e, lendo, rotula o que o bot DEVERIA ter entendido.
 *
 * ⚠️ SIMPLES DE PROPÓSITO. Filtro: só data. Sem agregados, sem gráficos, sem
 * busca. O painel é laboratório; complexidade prematura é o que faz
 * laboratório virar produto mal-acabado.
 */

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { MessageSquare, AlertTriangle, ChevronRight } from "lucide-react"
import { owner } from "@/lib/owner-api"
import { formatDateTime } from "@/lib/utils"
import type {
  TelemetryConversationList,
  TelemetryConversationRow,
} from "@/lib/telemetry-types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"

export default function OwnerTelemetriaPage() {
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")

  const [data, setData] = useState<TelemetryConversationList | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    const p = new URLSearchParams()
    if (dateFrom) p.set("date_from", dateFrom)
    // `date_to` é uma data pura; sem isto o filtro cortaria o próprio dia
    // escolhido (00:00 do dia seguinte inclui as mensagens da tarde).
    if (dateTo) p.set("date_to", `${dateTo}T23:59:59`)
    const qs = p.toString()
    try {
      setData(
        await owner.get<TelemetryConversationList>(
          `/platform/telemetry/conversations${qs ? `?${qs}` : ""}`,
        ),
      )
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo])

  useEffect(() => {
    load()
  }, [load])

  const items = data?.items ?? []
  const totalNotUnderstood = items.reduce((s, r) => s + r.not_understood_count, 0)

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Telemetria do bot"
        description="Conversas coletadas pelo trace. Abra uma para ler e marcar o que o bot deveria ter entendido."
      />

      {/* Filtro — só data, por decisão de escopo */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="space-y-1">
          <Label htmlFor="tel-from">De</Label>
          <Input
            id="tel-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="tel-to">Até</Label>
          <Input
            id="tel-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
        {(dateFrom || dateTo) && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setDateFrom("")
              setDateTo("")
            }}
          >
            Limpar
          </Button>
        )}
      </div>

      {loading ? (
        <Skeleton className="h-96 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : items.length === 0 ? (
        <EmptyState
          title="Nenhuma conversa"
          description="Nenhum trace no período. O bot grava uma linha por mensagem recebida."
        />
      ) : (
        <>
          <p className="text-sm text-muted-foreground">
            {items.length} {items.length === 1 ? "conversa" : "conversas"} ·{" "}
            {totalNotUnderstood}{" "}
            {totalNotUnderstood === 1
              ? "mensagem sem entendimento"
              : "mensagens sem entendimento"}
          </p>

          <div className="space-y-2">
            {items.map((c) => (
              <ConversationRow key={c.whatsapp_hash} row={c} />
            ))}
          </div>
        </>
      )}
    </div>
  )
}

function ConversationRow({ row }: { row: TelemetryConversationRow }) {
  const hasGap = row.not_understood_count > 0
  return (
    <Link
      href={`/owner/telemetria/${row.whatsapp_hash}`}
      className="flex items-center gap-4 rounded-lg border border-border bg-card px-4 py-3 transition-colors hover:border-primary/40 hover:bg-accent/40"
    >
      <div className="min-w-0 flex-1">
        <p className="truncate font-mono text-sm">
          {row.whatsapp_masked ?? row.whatsapp_hash}
        </p>
        <p className="truncate text-xs text-muted-foreground">
          {row.last_at ? formatDateTime(row.last_at) : "—"}
          {row.company_name ? ` · ${row.company_name}` : ""}
        </p>
      </div>

      <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <MessageSquare className="h-4 w-4" strokeWidth={1.5} />
        {row.message_count}
      </span>

      {/* O indicador que faz o Silva escolher qual conversa ler. */}
      {hasGap ? (
        <Badge variant="destructive" className="gap-1">
          <AlertTriangle className="h-3 w-3" strokeWidth={2} />
          {row.not_understood_count}
        </Badge>
      ) : (
        <Badge variant="outline" className="text-muted-foreground">
          0
        </Badge>
      )}

      <ChevronRight
        className="h-4 w-4 flex-shrink-0 text-muted-foreground"
        strokeWidth={1.5}
      />
    </Link>
  )
}
