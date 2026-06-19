"use client"

import { useEffect, useState } from "react"
import { toast } from "sonner"
import { ShieldAlert } from "lucide-react"
import { api } from "@/lib/api"
import { useImpersonation } from "@/context/ImpersonationContext"
import { IMPERSONATION_MODE_LABELS } from "@/lib/constants"

/** Formata os ms restantes como HH:MM (decrescente). */
function formatRemaining(ms: number): string {
  const totalMin = Math.max(0, Math.floor(ms / 60000))
  const h = Math.floor(totalMin / 60)
  const m = totalMin % 60
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`
}

/**
 * Faixa persistente exibida no topo de QUALQUER tela do owner enquanto houver
 * grant ativo. Sem botão de fechar — só "Encerrar" (revoga o grant) ou
 * expiração automática (countdown chega a zero).
 */
export function ImpersonationBanner() {
  const { activeGrant, endImpersonation } = useImpersonation()
  const [remaining, setRemaining] = useState<number>(0)
  const [ending, setEnding] = useState(false)

  useEffect(() => {
    if (!activeGrant) return
    const expiry = new Date(activeGrant.expires_at).getTime()

    function tick() {
      const ms = expiry - Date.now()
      setRemaining(ms)
      if (ms <= 0) {
        endImpersonation()
        toast.info("Sessão de impersonation expirada.")
      }
    }

    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [activeGrant, endImpersonation])

  if (!activeGrant) return null

  async function handleEnd() {
    if (!activeGrant) return
    setEnding(true)
    try {
      await api.delete(`/platform/impersonation/grants/${activeGrant.grant_id}`)
      toast.success("Acesso encerrado.")
    } catch (err: unknown) {
      // Mesmo se o DELETE falhar (ex.: já revogado), encerramos o estado local.
      toast.error((err as Error).message ?? "Erro ao encerrar acesso")
    } finally {
      endImpersonation()
      setEnding(false)
    }
  }

  const modeLabel = IMPERSONATION_MODE_LABELS[activeGrant.mode] ?? activeGrant.mode

  return (
    <div
      role="status"
      className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 bg-primary px-4 py-2 text-center text-sm text-primary-foreground"
    >
      <ShieldAlert size={16} strokeWidth={1.5} className="flex-shrink-0" />
      <span>
        Acessando como <strong>PLATFORM_OWNER</strong> em{" "}
        <strong>{activeGrant.company_name}</strong> · Modo <strong>{modeLabel}</strong> · Expira em{" "}
        <span className="font-mono tabular-nums">{formatRemaining(remaining)}</span>
      </span>
      <button
        type="button"
        onClick={handleEnd}
        disabled={ending}
        className="rounded-md border border-primary-foreground/40 px-2 py-0.5 text-xs font-medium transition-colors hover:bg-primary-foreground/15 disabled:opacity-60"
      >
        {ending ? "Encerrando…" : "Encerrar"}
      </button>
    </div>
  )
}
