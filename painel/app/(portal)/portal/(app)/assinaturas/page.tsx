"use client"

import { useEffect, useState } from "react"
import { CircleX, Loader2, PauseCircle, PlayCircle } from "lucide-react"
import { portal } from "@/lib/portal-api"
import { formatBRLFromDecimal, formatDateShort } from "@/lib/utils"
import { type PortalSubscriptionItem, establishmentLabel } from "@/lib/portal-types"
import { SubscriptionStatusBadge } from "@/components/portal/PortalStatusBadge"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

type Load = "loading" | "ok" | "error"
type Action = "pause" | "cancel" | "resume"

// B5 — cópia do diálogo de confirmação por ação (inclui "resume").
const DIALOG_COPY: Record<Action, { title: string; description: string; confirm: string }> = {
  pause: {
    title: "Pausar assinatura",
    description:
      "Deseja pausar esta assinatura? As cobranças ficam suspensas até a retomada.",
    confirm: "Sim, pausar",
  },
  cancel: {
    title: "Cancelar assinatura",
    description: "Tem certeza que deseja cancelar esta assinatura? Esta ação não pode ser desfeita.",
    confirm: "Sim, cancelar",
  },
  resume: {
    title: "Retomar assinatura",
    description: "Confirmar a retomada desta assinatura?",
    confirm: "Sim, retomar",
  },
}

export default function PortalAssinaturasPage() {
  const [state, setState] = useState<Load>("loading")
  const [subs, setSubs] = useState<PortalSubscriptionItem[]>([])

  // Diálogo de confirmação
  const [dialog, setDialog] = useState<{ id: string; action: Action } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  // Erro inline por assinatura
  const [errors, setErrors] = useState<Record<string, string>>({})

  function load() {
    setState("loading")
    portal
      .get<PortalSubscriptionItem[]>("/portal/subscriptions")
      .then((d) => {
        setSubs(d)
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

  async function confirmAction() {
    if (!dialog) return
    const { id, action } = dialog
    setSubmitting(true)
    setErrors((e) => ({ ...e, [id]: "" }))
    try {
      const updated = await portal.post<PortalSubscriptionItem>(
        `/portal/subscriptions/${id}/${action}`,
      )
      // Resultado inline: reflete o novo status na tela (sem toast).
      setSubs((list) => list.map((s) => (s.subscription_id === id ? { ...s, ...updated } : s)))
      setDialog(null)
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      const msg = (err as { message?: string }).message
      setErrors((e) => ({
        ...e,
        [id]:
          status === 403 || status === 422
            ? msg || "Esta ação não está disponível para este estabelecimento."
            : "Não foi possível concluir. Tente novamente.",
      }))
      setDialog(null)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Assinaturas</h1>

      {state === "loading" && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" &&
        (subs.length === 0 ? (
          <EmptyState
            title="Você não tem assinaturas"
            description="Planos recorrentes contratados aparecerão aqui."
          />
        ) : (
          <div className="space-y-3">
            {subs.map((s) => {
              const terminal = s.status === "CANCELLED" || s.status === "SUSPENDED"
              const isPaused = s.status === "PAUSED"
              return (
                <div
                  key={s.subscription_id}
                  className="rounded-xl bg-card p-4 ring-1 ring-foreground/10"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {s.plan_name ?? "Plano"}
                      </p>
                      <p className="truncate text-xs text-primary">{establishmentLabel(s)}</p>
                      {s.next_billing_at && (
                        <p className="mt-1 text-xs text-muted-foreground">
                          Próxima renovação: {formatDateShort(s.next_billing_at)}
                          {s.amount != null && ` · ${formatBRLFromDecimal(s.amount)}`}
                        </p>
                      )}
                    </div>
                    <SubscriptionStatusBadge status={s.status} />
                  </div>

                  {!terminal && (
                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      {isPaused ? (
                        // B5 — retomada agora exposta no Portal (POST .../resume).
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDialog({ id: s.subscription_id, action: "resume" })}
                        >
                          <PlayCircle size={14} strokeWidth={1.5} /> Retomar
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDialog({ id: s.subscription_id, action: "pause" })}
                        >
                          <PauseCircle size={14} strokeWidth={1.5} /> Pausar
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                        onClick={() => setDialog({ id: s.subscription_id, action: "cancel" })}
                      >
                        <CircleX size={14} strokeWidth={1.5} /> Cancelar
                      </Button>
                    </div>
                  )}

                  {errors[s.subscription_id] && (
                    <p className="mt-2 text-xs text-destructive">{errors[s.subscription_id]}</p>
                  )}
                </div>
              )
            })}
          </div>
        ))}

      {/* Dialog de confirmação (não AlertDialog — não existe no projeto) */}
      <Dialog open={dialog != null} onOpenChange={(o) => !submitting && !o && setDialog(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{dialog ? DIALOG_COPY[dialog.action].title : ""}</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {dialog ? DIALOG_COPY[dialog.action].description : ""}
          </p>
          <DialogFooter>
            <Button variant="outline" disabled={submitting} onClick={() => setDialog(null)}>
              Voltar
            </Button>
            <Button
              variant={dialog?.action === "cancel" ? "destructive" : "default"}
              disabled={submitting}
              onClick={confirmAction}
            >
              {submitting ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Processando…
                </>
              ) : dialog ? (
                DIALOG_COPY[dialog.action].confirm
              ) : (
                ""
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
