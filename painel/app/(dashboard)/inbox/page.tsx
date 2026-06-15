"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { Send, CheckCheck } from "lucide-react"
import { api } from "@/lib/api"
import { cn, formatDateTime, timeAgo } from "@/lib/utils"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

interface Conversation {
  session_id: string
  state: string
  phone: string
  customer_id?: string | null
  customer_name?: string | null
  last_message?: string | null
  escalated_at?: string | null
}

interface Message {
  direction: "INBOUND" | "OUTBOUND"
  content: string
  content_type: string
  sender_type: "CLIENT" | "BOT" | "AGENT"
  agent_user_id?: string | null
  created_at: string
}

const SENDER_LABEL: Record<string, string> = {
  CLIENT: "Cliente",
  BOT: "Bot",
  AGENT: "Atendente",
}

export default function InboxPage() {
  const [status, setStatus] = useState<"escalated" | "resolved">("escalated")
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [selected, setSelected] = useState<Conversation | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadList = useCallback(async (st: "escalated" | "resolved") => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<Conversation[]>(`/conversations?status=${st}`)
      setConversations(data)
      setSelected((prev) => data.find((c) => c.session_id === prev?.session_id) ?? data[0] ?? null)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadList(status) }, [status, loadList])

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operação"
        title="Atendimento humano"
        description="Conversas escaladas do bot para um atendente."
      />

      <div className="flex border-b border-border">
        {(["escalated", "resolved"] as const).map((st) => (
          <button
            key={st}
            onClick={() => setStatus(st)}
            aria-pressed={status === st}
            className={cn(
              "-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors",
              status === st
                ? "border-primary text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {st === "escalated" ? "Escaladas" : "Resolvidas"}
          </button>
        ))}
      </div>

      <InboxBody
        status={status}
        loading={loading} error={error}
        conversations={conversations} selected={selected}
        onSelect={setSelected} onRetry={() => loadList(status)}
        onChanged={() => loadList(status)}
      />
    </div>
  )
}

function InboxBody({
  status, loading, error, conversations, selected, onSelect, onRetry, onChanged,
}: {
  status: "escalated" | "resolved"
  loading: boolean
  error: string | null
  conversations: Conversation[]
  selected: Conversation | null
  onSelect: (c: Conversation) => void
  onRetry: () => void
  onChanged: () => void
}) {
  if (loading) return <Skeleton className="h-96 w-full" />
  if (error) return <ErrorState message={error} onRetry={onRetry} />
  if (conversations.length === 0) {
    return (
      <EmptyState
        title={status === "escalated" ? "Nenhuma conversa em atendimento" : "Nenhuma conversa resolvida"}
        description={status === "escalated" ? "Quando o bot escalar um atendimento, ele aparece aqui." : undefined}
      />
    )
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
      {/* Lista */}
      <div className="space-y-1.5">
        {conversations.map((c) => {
          const active = c.session_id === selected?.session_id
          return (
            <button
              key={c.session_id}
              onClick={() => onSelect(c)}
              className={cn(
                "w-full rounded-md border px-3 py-2.5 text-left transition-colors",
                active ? "border-primary bg-muted" : "border-border bg-card hover:bg-muted/50",
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium text-sm truncate">{c.customer_name ?? c.phone}</span>
                <Badge variant={status === "escalated" ? "secondary" : "outline"} className="shrink-0">
                  {status === "escalated" ? "Em atendimento" : "Resolvida"}
                </Badge>
              </div>
              {c.last_message && (
                <p className="mt-1 text-xs text-muted-foreground truncate">{c.last_message}</p>
              )}
              {status === "escalated" && c.escalated_at && (
                <p className="mt-1 text-[11px] text-muted-foreground">Esperando {timeAgo(c.escalated_at)}</p>
              )}
            </button>
          )
        })}
      </div>

      {/* Thread */}
      {selected ? (
        <ConversationThread conversation={selected} onChanged={onChanged} />
      ) : (
        <EmptyState title="Selecione uma conversa" />
      )}
    </div>
  )
}

function ConversationThread({
  conversation, onChanged,
}: { conversation: Conversation; onChanged: () => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [reply, setReply] = useState("")
  const [sending, setSending] = useState(false)
  const [resolveOpen, setResolveOpen] = useState(false)
  const [resolving, setResolving] = useState(false)

  const isHuman = conversation.state === "HUMANO"

  const loadMessages = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<Message[]>(`/conversations/${conversation.session_id}/messages`)
      setMessages(data)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [conversation.session_id])

  useEffect(() => { loadMessages() }, [loadMessages])

  async function handleSend() {
    if (!reply.trim()) return
    setSending(true)
    try {
      await api.post(`/conversations/${conversation.session_id}/reply`, { content: reply })
      setReply("")
      toast.success("Mensagem enviada")
      loadMessages()
    } catch (err: unknown) {
      const msg = (err as Error).message
      toast.error(msg?.includes("HUMANO") ? "Conversa não está em atendimento humano." : msg ?? "Erro ao enviar")
    } finally {
      setSending(false)
    }
  }

  async function handleResolve() {
    setResolving(true)
    try {
      await api.patch(`/conversations/${conversation.session_id}/resolve`, {})
      setResolveOpen(false)
      toast.success("Bot reassumiu o atendimento")
      onChanged()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao resolver")
    } finally {
      setResolving(false)
    }
  }

  return (
    <div className="flex flex-col rounded-md border border-border bg-card">
      <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <p className="font-medium text-sm truncate">{conversation.customer_name ?? conversation.phone}</p>
          <p className="text-xs text-muted-foreground">{conversation.phone}</p>
        </div>
        {isHuman && (
          <Dialog open={resolveOpen} onOpenChange={setResolveOpen}>
            <DialogTrigger render={<Button size="sm" variant="outline" />}>
              <CheckCheck size={16} strokeWidth={1.5} /> Resolver
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Resolver conversa</DialogTitle>
                <DialogDescription>
                  O bot reassume o atendimento na próxima mensagem do cliente. Confirmar?
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <Button variant="outline" onClick={() => setResolveOpen(false)}>Cancelar</Button>
                <Button onClick={handleResolve} disabled={resolving}>
                  {resolving ? "Resolvendo…" : "Confirmar"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4 max-h-[55vh] min-h-64">
        {loading ? (
          <Skeleton className="h-40 w-full" />
        ) : error ? (
          <ErrorState message={error} onRetry={loadMessages} />
        ) : messages.length === 0 ? (
          <EmptyState message="Sem mensagens nesta conversa." />
        ) : (
          messages.map((m, i) => {
            const fromClient = m.sender_type === "CLIENT"
            return (
              <div key={i} className={cn("flex flex-col", fromClient ? "items-start" : "items-end")}>
                <div
                  className={cn(
                    "max-w-[75%] rounded-lg px-3 py-2 text-sm",
                    fromClient ? "bg-muted text-foreground" : "bg-primary text-primary-foreground",
                  )}
                >
                  {m.content}
                </div>
                <span className="mt-1 text-[10px] text-muted-foreground">
                  {SENDER_LABEL[m.sender_type] ?? m.sender_type} · {formatDateTime(m.created_at)}
                </span>
              </div>
            )
          })
        )}
      </div>

      <div className="border-t border-border p-3">
        {isHuman ? (
          <div className="flex items-end gap-2">
            <Textarea
              value={reply}
              onChange={(e) => setReply(e.target.value)}
              placeholder="Escreva uma resposta…"
              rows={2}
              className="flex-1 resize-none"
            />
            <Button onClick={handleSend} disabled={sending || !reply.trim()}>
              <Send size={16} strokeWidth={1.5} /> Enviar
            </Button>
          </div>
        ) : (
          <p className="text-center text-xs text-muted-foreground py-2">
            Conversa não está em atendimento humano — respostas desabilitadas.
          </p>
        )}
      </div>
    </div>
  )
}
