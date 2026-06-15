"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { Pencil, Trash2, Plus } from "lucide-react"
import { api } from "@/lib/api"
import {
  COMMUNICATION_EVENT_TYPE_LABELS,
  COMMUNICATION_EVENT_TYPE_OPTIONS,
  COMMUNICATION_CHANNEL_LABELS,
  COMMUNICATION_AUDIENCE_LABELS,
  TEMPLATE_VARIABLES_BY_EVENT,
  TEMPLATE_VARIABLE_EXAMPLES,
} from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Textarea } from "@/components/ui/textarea"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface Template {
  template_id: string
  company_id: string
  event_type: string
  channel: string
  audience: string
  body_template: string
  is_active: boolean
  is_default: boolean
}

const CHANNELS = ["WHATSAPP", "EMAIL", "SMS"]
const AUDIENCES = ["CLIENT", "PROFESSIONAL", "OWNER"]

// Substitui {{var}} por valores de exemplo (preview visual apenas)
function renderPreview(body: string): string {
  return body.replace(/\{\{(\w+)\}\}/g, (_, v) => TEMPLATE_VARIABLE_EXAMPLES[v] ?? `{{${v}}}`)
}

/* ------------------------------ Preview de canal ------------------------------ */
function ChannelPreview({ channel, body }: { channel: string; body: string }) {
  const text = body.trim() ? renderPreview(body) : "Mensagem aparece aqui…"
  if (channel === "WHATSAPP") {
    return (
      <div className="rounded-lg bg-emerald-950/30 p-4 min-h-32">
        <div className="max-w-[85%] rounded-xl rounded-tl-sm bg-emerald-600 px-3 py-2 text-sm text-white whitespace-pre-wrap shadow">
          {text}
        </div>
      </div>
    )
  }
  if (channel === "EMAIL") {
    return (
      <div className="rounded-lg border border-border bg-card p-4 min-h-32">
        <div className="border-b border-border pb-2 text-xs text-muted-foreground">Assunto: (definido pelo sistema)</div>
        <p className="pt-3 text-sm whitespace-pre-wrap">{text}</p>
      </div>
    )
  }
  return (
    <div className="rounded-lg border border-border bg-muted/40 p-4 min-h-32">
      <p className="text-xs text-muted-foreground mb-2">SMS</p>
      <p className="text-sm whitespace-pre-wrap">{text}</p>
    </div>
  )
}

/* ------------------------------ Dialog de template ------------------------------ */
function TemplateDialog({ open, onOpenChange, editing, onSaved }: {
  open: boolean
  onOpenChange: (v: boolean) => void
  editing: Template | null
  onSaved: () => void
}) {
  const isEdit = !!editing
  const [eventType, setEventType] = useState("appointment.confirmed")
  const [channel, setChannel] = useState("WHATSAPP")
  const [audience, setAudience] = useState("CLIENT")
  const [body, setBody] = useState("")
  const [isActive, setIsActive] = useState(true)
  const [saving, setSaving] = useState(false)
  const bodyRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (!open) return
    if (editing) {
      setEventType(editing.event_type)
      setChannel(editing.channel)
      setAudience(editing.audience)
      setBody(editing.body_template)
      setIsActive(editing.is_active)
    } else {
      setEventType("appointment.confirmed")
      setChannel("WHATSAPP")
      setAudience("CLIENT")
      setBody("")
      setIsActive(true)
    }
  }, [open, editing])

  const variables = TEMPLATE_VARIABLES_BY_EVENT[eventType] ?? []

  function insertVariable(v: string) {
    const token = `{{${v}}}`
    const el = bodyRef.current
    if (!el) { setBody((b) => b + token); return }
    const start = el.selectionStart ?? body.length
    const end = el.selectionEnd ?? body.length
    const next = body.slice(0, start) + token + body.slice(end)
    setBody(next)
    requestAnimationFrame(() => {
      el.focus()
      const pos = start + token.length
      el.setSelectionRange(pos, pos)
    })
  }

  async function handleSave() {
    if (!body.trim()) return
    setSaving(true)
    try {
      if (isEdit && editing) {
        await api.put(`/communication/templates/${editing.template_id}`, {
          body_template: body,
          is_active: isActive,
        })
        toast.success("Template atualizado")
      } else {
        await api.post("/communication/templates", {
          event_type: eventType,
          channel,
          audience,
          body_template: body,
          is_active: isActive,
          is_default: false,
        })
        toast.success("Template criado")
      }
      onOpenChange(false)
      onSaved()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar template")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar template" : "Novo template"}</DialogTitle>
        </DialogHeader>

        <div className="grid gap-6 py-1 md:grid-cols-2">
          {/* Form */}
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Evento</Label>
              {isEdit ? (
                <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                  {COMMUNICATION_EVENT_TYPE_LABELS[eventType] ?? eventType}
                </p>
              ) : (
                <Select value={eventType} onValueChange={(v) => v && setEventType(v)}>
                  <SelectTrigger className="w-full">
                    <SelectValue>{COMMUNICATION_EVENT_TYPE_LABELS[eventType] ?? eventType}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {COMMUNICATION_EVENT_TYPE_OPTIONS.map((e) => (
                      <SelectItem key={e} value={e}>{COMMUNICATION_EVENT_TYPE_LABELS[e]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Canal</Label>
                {isEdit ? (
                  <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                    {COMMUNICATION_CHANNEL_LABELS[channel] ?? channel}
                  </p>
                ) : (
                  <Select value={channel} onValueChange={(v) => v && setChannel(v)}>
                    <SelectTrigger className="w-full">
                      <SelectValue>{COMMUNICATION_CHANNEL_LABELS[channel] ?? channel}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {CHANNELS.map((c) => <SelectItem key={c} value={c}>{COMMUNICATION_CHANNEL_LABELS[c]}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              </div>
              <div className="space-y-1.5">
                <Label>Público</Label>
                {isEdit ? (
                  <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
                    {COMMUNICATION_AUDIENCE_LABELS[audience] ?? audience}
                  </p>
                ) : (
                  <Select value={audience} onValueChange={(v) => v && setAudience(v)}>
                    <SelectTrigger className="w-full">
                      <SelectValue>{COMMUNICATION_AUDIENCE_LABELS[audience] ?? audience}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {AUDIENCES.map((a) => <SelectItem key={a} value={a}>{COMMUNICATION_AUDIENCE_LABELS[a]}</SelectItem>)}
                    </SelectContent>
                  </Select>
                )}
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="tpl-body">Corpo</Label>
              <Textarea
                id="tpl-body" ref={bodyRef} value={body} rows={6}
                onChange={(e) => setBody(e.target.value)}
                placeholder="Digite o corpo da mensagem…"
              />
            </div>

            {variables.length > 0 && (
              <div className="space-y-2">
                <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Variáveis disponíveis</p>
                <div className="flex flex-wrap gap-1.5">
                  {variables.map((v) => (
                    <button
                      key={v} type="button" onClick={() => insertVariable(v)}
                      className="rounded-md border border-border bg-muted/40 px-2 py-1 font-mono text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                    >
                      {`{{${v}}}`}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <Label htmlFor="tpl-active">Ativo</Label>
              <Switch id="tpl-active" checked={isActive} onCheckedChange={setIsActive} />
            </div>
          </div>

          {/* Preview */}
          <div className="space-y-2">
            <p className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground">Pré-visualização</p>
            <ChannelPreview channel={channel} body={body} />
          </div>
        </div>

        <DialogFooter>
          <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
          <Button onClick={handleSave} disabled={saving || !body.trim()}>
            {saving ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------- Página ---------------------------------- */
export default function TemplatesPage() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Template | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Template | null>(null)
  const [deleting, setDeleting] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setTemplates(await api.get<Template[]>("/communication/templates"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await api.delete(`/communication/templates/${deleteTarget.template_id}`)
      toast.success("Template excluído")
      setDeleteTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao excluir")
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Comunicação" title="Templates" description="Mensagens automáticas por evento, canal e público.">
        <Button variant="outline" render={<Link href="/comunicacao/logs" />}>Logs</Button>
        <Button onClick={() => { setEditing(null); setDialogOpen(true) }}>
          <Plus className="h-4 w-4" /> Novo template
        </Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <Tabs defaultValue="all">
          <TabsList>
            <TabsTrigger value="all">Todos</TabsTrigger>
            <TabsTrigger value="WHATSAPP">WhatsApp</TabsTrigger>
            <TabsTrigger value="EMAIL">E-mail</TabsTrigger>
            <TabsTrigger value="SMS">SMS</TabsTrigger>
          </TabsList>
          {["all", "WHATSAPP", "EMAIL", "SMS"].map((ch) => {
            const rows = ch === "all" ? templates : templates.filter((t) => t.channel === ch)
            return (
              <TabsContent key={ch} value={ch}>
                {rows.length === 0 ? (
                  <EmptyState title="Nenhum template" description="Crie um template para este canal." />
                ) : (
                  <div className="overflow-x-auto rounded-lg border border-border">
                    <table className="w-full text-sm">
                      <thead className="bg-muted/50 text-muted-foreground">
                        <tr>
                          <th className="px-4 py-3 text-left font-medium">Evento</th>
                          <th className="px-4 py-3 text-left font-medium">Canal</th>
                          <th className="px-4 py-3 text-left font-medium">Público</th>
                          <th className="px-4 py-3 text-left font-medium">Ativo</th>
                          <th className="px-4 py-3 text-left font-medium">Padrão</th>
                          <th className="px-4 py-3 text-right font-medium">Ações</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border">
                        {rows.map((t) => (
                          <tr key={t.template_id} className="transition-colors hover:bg-muted/30">
                            <td className="px-4 py-3 font-medium">{COMMUNICATION_EVENT_TYPE_LABELS[t.event_type] ?? t.event_type}</td>
                            <td className="px-4 py-3 text-muted-foreground">{COMMUNICATION_CHANNEL_LABELS[t.channel] ?? t.channel}</td>
                            <td className="px-4 py-3 text-muted-foreground">{COMMUNICATION_AUDIENCE_LABELS[t.audience] ?? t.audience}</td>
                            <td className="px-4 py-3"><ActiveBadge active={t.is_active} /></td>
                            <td className="px-4 py-3">{t.is_default && <Badge variant="outline">Padrão</Badge>}</td>
                            <td className="px-4 py-3">
                              <div className="flex items-center justify-end gap-1">
                                <Button size="icon-sm" variant="ghost" aria-label="Editar"
                                  onClick={() => { setEditing(t); setDialogOpen(true) }}>
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button size="icon-sm" variant="ghost" className="text-destructive" aria-label="Excluir"
                                  onClick={() => setDeleteTarget(t)}>
                                  <Trash2 className="h-4 w-4" />
                                </Button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </TabsContent>
            )
          })}
        </Tabs>
      )}

      <TemplateDialog open={dialogOpen} onOpenChange={setDialogOpen} editing={editing} onSaved={load} />

      {/* Excluir */}
      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir template</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {deleteTarget?.is_default
              ? "Este é um template padrão semeado pelo sistema. A exclusão pode ser recusada pelo backend."
              : "Esta ação não pode ser desfeita."}
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDelete} disabled={deleting}>
              {deleting ? "Excluindo…" : "Excluir"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
