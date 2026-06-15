"use client"

import { use, useState } from "react"
import { CheckCircle2, Loader2 } from "lucide-react"
import { publicFetch } from "@/lib/api"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"

type Phase = "idle" | "sending" | "success" | "error"

// Faixa NPS visual: 0–6 detrator · 7–8 neutro · 9–10 promotor
function scoreClass(n: number, selected: boolean): string {
  const base =
    n <= 6 ? "border-destructive/40 text-destructive hover:bg-destructive/10"
    : n <= 8 ? "border-amber-500/40 text-amber-600 hover:bg-amber-500/10 dark:text-amber-300"
    : "border-emerald-500/40 text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-300"
  const sel =
    n <= 6 ? "bg-destructive/15 ring-2 ring-destructive/40"
    : n <= 8 ? "bg-amber-500/15 ring-2 ring-amber-500/40"
    : "bg-emerald-500/15 ring-2 ring-emerald-500/40"
  return cn(base, selected && sel)
}

export default function NpsRespondPage({ params }: { params: Promise<{ survey_id: string }> }) {
  const { survey_id } = use(params)

  const [score, setScore] = useState<number | null>(null)
  const [comment, setComment] = useState("")
  const [phase, setPhase] = useState<Phase>("idle")
  const [errorMsg, setErrorMsg] = useState("")

  async function handleSubmit() {
    if (score === null) return
    setPhase("sending")
    try {
      await publicFetch(`/nps/respond/${survey_id}`, {
        method: "POST",
        body: JSON.stringify({ score, comment: comment.trim() || undefined }),
      })
      setPhase("success")
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      // 422 = survey indisponível (já respondida / expirada)
      setErrorMsg(
        status === 422
          ? "Esta pesquisa não está mais disponível."
          : "Não foi possível enviar, tente novamente.",
      )
      setPhase("error")
    }
  }

  return (
    <div className="book-page min-h-screen bg-background flex items-center justify-center px-4 py-12">
      <div className="w-full max-w-md">
        <div className="mb-8 text-center">
          <span className="font-display text-2xl tracking-[0.3em] text-primary">PALADINO</span>
        </div>

        <div className="rounded-2xl border border-border bg-card p-8 shadow-sm">
          {phase === "success" ? (
            <div className="flex flex-col items-center gap-3 py-8 text-center">
              <CheckCircle2 className="h-12 w-12 text-emerald-500" strokeWidth={1.5} />
              <h1 className="font-display text-2xl">Obrigado pelo seu feedback!</h1>
              <p className="text-sm text-muted-foreground">
                Sua avaliação foi registrada com sucesso.
              </p>
            </div>
          ) : (
            <>
              <h1 className="font-display text-3xl tracking-wide text-center">Como foi sua experiência?</h1>
              <p className="mt-2 mb-6 text-center text-sm text-muted-foreground">
                De 0 a 10, o quanto você recomendaria nosso atendimento?
              </p>

              <div className="grid grid-cols-6 gap-2 sm:grid-cols-11">
                {Array.from({ length: 11 }, (_, n) => (
                  <button
                    key={n}
                    type="button"
                    onClick={() => setScore(n)}
                    disabled={phase === "sending"}
                    className={cn(
                      "aspect-square rounded-lg border text-sm font-medium tabular-nums transition-colors disabled:opacity-50",
                      scoreClass(n, score === n),
                    )}
                    aria-pressed={score === n}
                  >
                    {n}
                  </button>
                ))}
              </div>

              <div className="mt-3 flex justify-between text-[11px] text-muted-foreground">
                <span>Pouco provável</span>
                <span>Muito provável</span>
              </div>

              <div className="mt-6 space-y-1.5">
                <label htmlFor="nps-comment" className="text-sm text-muted-foreground">
                  Comentário (opcional)
                </label>
                <Textarea
                  id="nps-comment"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  maxLength={2000}
                  rows={4}
                  placeholder="Conte mais sobre sua experiência…"
                  disabled={phase === "sending"}
                />
              </div>

              {phase === "error" && (
                <p className="mt-4 text-center text-sm text-destructive">{errorMsg}</p>
              )}

              <Button
                className="mt-6 w-full"
                size="lg"
                onClick={handleSubmit}
                disabled={score === null || phase === "sending"}
              >
                {phase === "sending" ? (
                  <><Loader2 className="h-4 w-4 animate-spin" /> Enviando…</>
                ) : "Enviar"}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
