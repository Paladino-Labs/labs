"use client"

/**
 * Telemetria do bot — uma conversa (S-painel-telemetria).
 *
 * Formato de chat: cliente de um lado, bot do outro, em ordem. Por mensagem
 * do cliente ficam INLINE o texto, se o bot entendeu (e o quê) e se devolveu
 * menu genérico — o sintoma que interessa. O diagnóstico completo fica atrás
 * do expansível: tudo inline vira ruído, pouco demais não explica.
 *
 * ⚠️ MARCAR NÃO RECARREGA A TELA. Cada marcação é um PUT isolado com estado
 * local otimista. Marcar 40 mensagens com reload a cada uma inviabiliza o uso
 * — este é o requisito que define a tela, não um detalhe de implementação.
 *
 * ⚠️ Marcar é OPCIONAL por mensagem: o que está certo fica em branco. Nada
 * aqui exige preencher para avançar.
 */

import { useCallback, useEffect, useMemo, useState } from "react"
import { useParams, useRouter } from "next/navigation"
import Link from "next/link"
import {
  ArrowLeft, ChevronDown, ChevronRight, AlertTriangle, Check,
  MessageSquarePlus, Bot, User as UserIcon,
} from "lucide-react"
import { owner } from "@/lib/owner-api"
import { cn, formatDateTime } from "@/lib/utils"
import {
  EXPECTED_INTENT_LABELS,
  NOT_UNDERSTOOD_REASON_LABELS,
  UNDERSTOOD_LABELS,
  type TelemetryCatalog,
  type TelemetryConversation,
  type TelemetryConversationList,
  type TelemetryLabel,
  type TelemetryLabelResponse,
  type TelemetryMessage,
} from "@/lib/telemetry-types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"

const UNDERSTOOD_ORDER = ["YES", "NO", "WRONG"] as const

export default function OwnerTelemetriaConversaPage() {
  const params = useParams<{ hash: string }>()
  const router = useRouter()
  const hash = params?.hash

  const [convo, setConvo] = useState<TelemetryConversation | null>(null)
  const [catalog, setCatalog] = useState<TelemetryCatalog | null>(null)
  const [siblings, setSiblings] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!hash) return
    setLoading(true)
    setError(null)
    try {
      const [c, cat] = await Promise.all([
        owner.get<TelemetryConversation>(
          `/platform/telemetry/conversations/${encodeURIComponent(hash)}`,
        ),
        owner.get<TelemetryCatalog>("/platform/telemetry/catalog"),
      ])
      setConvo(c)
      setCatalog(cat)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [hash])

  useEffect(() => {
    load()
  }, [load])

  // Navegação rápida entre conversas: a lista é barata (~25 linhas) e é o que
  // permite ler uma atrás da outra sem voltar ao índice a cada uma.
  useEffect(() => {
    let alive = true
    owner
      .get<TelemetryConversationList>("/platform/telemetry/conversations")
      .then((d) => {
        if (alive) setSiblings(d.items.map((i) => i.whatsapp_hash))
      })
      .catch(() => {
        /* navegação é conforto; a conversa já está na tela */
      })
    return () => {
      alive = false
    }
  }, [])

  const { prev, next } = useMemo(() => {
    const i = siblings.indexOf(hash ?? "")
    if (i < 0) return { prev: null, next: null }
    return {
      prev: i > 0 ? siblings[i - 1] : null,
      next: i < siblings.length - 1 ? siblings[i + 1] : null,
    }
  }, [siblings, hash])

  /** Estado otimista: a tela já mostra o rótulo novo; o PUT confirma atrás. */
  const applyLabel = useCallback((traceId: string, label: TelemetryLabel | null) => {
    setConvo((c) =>
      c
        ? {
            ...c,
            messages: c.messages.map((m) =>
              m.trace_id === traceId ? { ...m, label } : m,
            ),
          }
        : c,
    )
  }, [])

  if (loading) return <Skeleton className="h-96 w-full" />
  if (error) return <ErrorState message={error} onRetry={load} />
  if (!convo) {
    return <EmptyState title="Conversa não encontrada" description="O trace pode ter passado da retenção de 30 dias." />
  }

  const marked = convo.messages.filter((m) => m.label).length

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/owner/telemetria"
          className="flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
          Todas as conversas
        </Link>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={!prev}
            onClick={() => prev && router.push(`/owner/telemetria/${prev}`)}
          >
            Anterior
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={!next}
            onClick={() => next && router.push(`/owner/telemetria/${next}`)}
          >
            Próxima
          </Button>
        </div>
      </div>

      <PageHeader
        eyebrow="Telemetria do bot"
        title={convo.whatsapp_masked ?? convo.whatsapp_hash}
        description={`${convo.message_count} ${convo.message_count === 1 ? "mensagem" : "mensagens"} · ${convo.not_understood_count} sem entendimento · ${marked} ${marked === 1 ? "marcada" : "marcadas"}`}
      />

      <div className="space-y-5">
        {convo.messages.map((m) => (
          <MessageBlock
            key={m.trace_id}
            message={m}
            intents={catalog?.expected_intents ?? []}
            onLabel={applyLabel}
          />
        ))}
      </div>
    </div>
  )
}

/* ─── Uma mensagem: o que o cliente disse, o que o bot fez, e a marcação ──── */

function MessageBlock({
  message,
  intents,
  onLabel,
}: {
  message: TelemetryMessage
  intents: string[]
  onLabel: (traceId: string, label: TelemetryLabel | null) => void
}) {
  const [open, setOpen] = useState(false)
  const d = message.diagnosis

  return (
    <div className="space-y-2">
      {/* Cliente — esquerda */}
      <div className="flex gap-3">
        <span className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-muted">
          <UserIcon className="h-3.5 w-3.5 text-muted-foreground" strokeWidth={1.5} />
        </span>
        <div className="min-w-0 flex-1 space-y-2">
          <div
            className={cn(
              "rounded-lg rounded-tl-none border bg-card px-4 py-3",
              d.not_understood ? "border-destructive/40" : "border-border",
            )}
          >
            <p className="whitespace-pre-wrap break-words text-sm">
              {message.text || (
                <span className="italic text-muted-foreground">
                  (sem texto — {message.detail.message_type ?? "tipo desconhecido"})
                </span>
              )}
            </p>

            {/* Inline: entendeu? o quê? devolveu menu genérico? */}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              {d.classified && d.intent ? (
                <Badge variant="outline" className="font-mono text-[11px]">
                  {d.intent}
                  {typeof d.confidence === "number" ? ` · ${d.confidence.toFixed(2)}` : ""}
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[11px] text-muted-foreground">
                  não classificada
                </Badge>
              )}
              {d.generic_menu && (
                <Badge variant="destructive" className="gap-1 text-[11px]">
                  <AlertTriangle className="h-3 w-3" strokeWidth={2} />
                  {NOT_UNDERSTOOD_REASON_LABELS[d.reason ?? ""] ?? "Menu genérico"}
                </Badge>
              )}
              {d.not_understood && !d.generic_menu && (
                <Badge variant="destructive" className="text-[11px]">
                  {NOT_UNDERSTOOD_REASON_LABELS[d.reason ?? ""] ?? d.reason}
                </Badge>
              )}
              <span className="ml-auto text-[11px] text-muted-foreground">
                {message.received_at ? formatDateTime(message.received_at) : "—"}
              </span>
            </div>
          </div>

          <LabelRow message={message} intents={intents} onLabel={onLabel} />

          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
          >
            {open ? (
              <ChevronDown className="h-3.5 w-3.5" strokeWidth={1.5} />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" strokeWidth={1.5} />
            )}
            Diagnóstico
          </button>
          {open && <DiagnosticPanel message={message} />}
        </div>
      </div>

      {/* Bot — direita */}
      {message.outbound.length > 0 && (
        <div className="flex flex-row-reverse gap-3">
          <span className="mt-1 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-primary/10">
            <Bot className="h-3.5 w-3.5 text-primary" strokeWidth={1.5} />
          </span>
          <div className="min-w-0 flex-1 space-y-1.5">
            {message.outbound.map((o, i) => (
              <div
                key={i}
                className={cn(
                  "ml-auto max-w-[85%] rounded-lg rounded-tr-none border px-4 py-2.5",
                  o.ok ? "border-border bg-muted/40" : "border-destructive/40 bg-destructive/5",
                )}
              >
                <p className="whitespace-pre-wrap break-words text-sm text-muted-foreground">
                  {o.text || <span className="italic">(vazio)</span>}
                </p>
                <p className="mt-1 text-right font-mono text-[10px] text-muted-foreground/70">
                  {o.kind}
                  {o.ok ? "" : " · falhou"}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ─── A marcação ──────────────────────────────────────────────────────────── */

function LabelRow({
  message,
  intents,
  onLabel,
}: {
  message: TelemetryMessage
  intents: string[]
  onLabel: (traceId: string, label: TelemetryLabel | null) => void
}) {
  const label = message.label
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState(label?.note ?? "")
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  const save = useCallback(
    async (next: TelemetryLabel) => {
      const isEmpty =
        !next.understood && !next.expected_intent && !(next.note ?? "").trim()
      // Otimista: a tela responde já; o PUT confirma atrás.
      onLabel(message.trace_id, isEmpty ? null : next)
      setSaving(true)
      setSaveError(null)
      try {
        const res = await owner.put<TelemetryLabelResponse>(
          `/platform/telemetry/labels/${message.trace_id}`,
          {
            understood: next.understood,
            expected_intent: next.expected_intent,
            note: next.note,
          },
        )
        onLabel(message.trace_id, res.label)
        setSaved(true)
        setTimeout(() => setSaved(false), 1500)
      } catch (err: unknown) {
        // Reverte para o que o servidor tinha — marcação que não gravou não
        // pode ficar parecendo gravada, senão o dado final mente.
        onLabel(message.trace_id, label)
        setSaveError((err as Error).message)
      } finally {
        setSaving(false)
      }
    },
    [message.trace_id, label, onLabel],
  )

  function setUnderstood(v: string) {
    // Clicar no valor já marcado desmarca — é como se corrige sem menu.
    const understood = label?.understood === v ? null : v
    save({
      understood,
      expected_intent: label?.expected_intent ?? null,
      note: label?.note ?? null,
    })
  }

  function setIntent(v: string) {
    const expected_intent = label?.expected_intent === v ? null : v
    save({
      understood: label?.understood ?? null,
      expected_intent,
      note: label?.note ?? null,
    })
  }

  function commitNote() {
    const trimmed = note.trim()
    if (trimmed === (label?.note ?? "")) return
    save({
      understood: label?.understood ?? null,
      expected_intent: label?.expected_intent ?? null,
      note: trimmed || null,
    })
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed border-border/70 px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {/* O bot entendeu? */}
        <div className="flex items-center gap-1">
          {UNDERSTOOD_ORDER.map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setUnderstood(v)}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                label?.understood === v
                  ? v === "YES"
                    ? "bg-primary/15 text-primary"
                    : "bg-destructive/15 text-destructive"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {UNDERSTOOD_LABELS[v]}
            </button>
          ))}
        </div>

        <span className="h-4 w-px bg-border" />

        {/* O que era? */}
        <div className="flex flex-wrap items-center gap-1">
          {intents.map((it) => (
            <button
              key={it}
              type="button"
              onClick={() => setIntent(it)}
              className={cn(
                "rounded-md px-2 py-1 text-xs transition-colors",
                label?.expected_intent === it
                  ? "bg-secondary text-secondary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground",
              )}
            >
              {EXPECTED_INTENT_LABELS[it] ?? it}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => setNoteOpen((v) => !v)}
          className="ml-auto flex items-center gap-1 rounded-md px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" strokeWidth={1.5} />
          Observação
        </button>

        <span className="w-14 text-right text-[11px] text-muted-foreground">
          {saving ? "salvando…" : saved ? (
            <span className="inline-flex items-center gap-0.5 text-primary">
              <Check className="h-3 w-3" strokeWidth={2} /> salvo
            </span>
          ) : null}
        </span>
      </div>

      {(noteOpen || label?.note) && (
        <Input
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={commitNote}
          onKeyDown={(e) => {
            if (e.key === "Enter") e.currentTarget.blur()
          }}
          placeholder="O que não cabe em rótulo…"
          className="h-8 text-xs"
        />
      )}

      {saveError && (
        <p className="text-xs text-destructive">Não gravou: {saveError}</p>
      )}
    </div>
  )
}

/* ─── O expansível ────────────────────────────────────────────────────────── */

function DiagnosticPanel({ message }: { message: TelemetryMessage }) {
  const d = message.detail
  return (
    <div className="space-y-3 rounded-lg border border-border bg-muted/30 p-3">
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3">
        <Field label="Estado na chegada" value={d.fsm_state} />
        <Field label="Estado após" value={d.fsm_state_after} />
        <Field label="Tipo da mensagem" value={d.message_type} />
        <Field label="Desfecho" value={d.outcome} />
        <Field label="Handler" value={d.handler} />
        <Field
          label="Decisão de roteamento"
          value={(d.routing?.decision as string) ?? null}
        />
        <Field
          label="Regex"
          value={
            d.regex
              ? `${d.regex.intent ?? "—"} · ${Number(d.regex.confidence ?? 0).toFixed(2)}${d.regex.matched ? "" : " (não casou)"}`
              : null
          }
        />
        <Field
          label="LLM"
          value={
            d.llm
              ? `${d.llm.intent ?? "—"} · ${Number(d.llm.confidence ?? 0).toFixed(2)}`
              : null
          }
        />
        <Field
          label="Duração"
          value={d.duration_ms != null ? `${d.duration_ms} ms` : null}
        />
      </dl>

      {d.dispatch_path && d.dispatch_path.length > 0 && (
        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground">
            Caminho
          </p>
          <p className="font-mono text-xs">{d.dispatch_path.join(" → ")}</p>
        </div>
      )}

      {d.dispatch_detail && Object.keys(d.dispatch_detail).length > 0 && (
        <pre className="max-h-48 overflow-auto rounded-md border border-border bg-background p-2 text-[11px]">
          {JSON.stringify(d.dispatch_detail, null, 2)}
        </pre>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd className="truncate font-mono text-xs" title={value ?? undefined}>
        {value ?? "—"}
      </dd>
    </div>
  )
}
