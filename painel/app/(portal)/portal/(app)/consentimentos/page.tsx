"use client"

import { useEffect, useMemo, useState } from "react"
import { AlertTriangle } from "lucide-react"
import { portal } from "@/lib/portal-api"
import type { PortalConsentRecord } from "@/lib/portal-types"
import { CONSENT_CHANNEL_LABELS, CONSENT_TYPE_LABELS } from "@/lib/constants"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"

const CHANNELS = ["WHATSAPP", "EMAIL", "SMS"] as const

// Defaults quando NÃO há registro (espelha consent_service.py):
//   COMMUNICATION → GRANTED (opt-out) · demais → REVOKED (opt-in).
function defaultGranted(type: string): boolean {
  return type === "COMMUNICATION"
}

function key(type: string, channel: string | null): string {
  return `${type}:${channel ?? "*"}`
}

export default function PortalConsentimentosPage() {
  const [state, setState] = useState<Load>("loading")
  // Estado efetivo (otimista) por chave type:channel.
  const [granted, setGranted] = useState<Record<string, boolean>>({})
  const [toggleError, setToggleError] = useState<string | null>(null)

  function load() {
    setState("loading")
    portal
      .get<PortalConsentRecord[]>("/portal/consents")
      .then((records) => {
        // Registro mais recente por (type, channel) define o estado vigente.
        const latest = new Map<string, PortalConsentRecord>()
        for (const r of records) {
          const k = key(r.consent_type, r.channel)
          const prev = latest.get(k)
          if (!prev || new Date(r.occurred_at) > new Date(prev.occurred_at)) latest.set(k, r)
        }
        const map: Record<string, boolean> = {}
        latest.forEach((r, k) => {
          map[k] = r.status === "GRANTED"
        })
        setGranted(map)
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

  function isOn(type: string, channel: string | null): boolean {
    const k = key(type, channel)
    return k in granted ? granted[k] : defaultGranted(type)
  }

  async function toggle(type: string, channel: string | null) {
    const k = key(type, channel)
    const next = !isOn(type, channel)
    setToggleError(null)
    // Otimista: aplica na hora.
    setGranted((g) => ({ ...g, [k]: next }))
    try {
      const path = next ? "/portal/consents/grant" : "/portal/consents/revoke"
      await portal.post(path, { consent_type: type, ...(channel ? { channel } : {}) })
    } catch {
      // Reverte em erro.
      setGranted((g) => ({ ...g, [k]: !next }))
      setToggleError("Não foi possível atualizar a preferência. Tente novamente.")
    }
  }

  const dataProcessingOff = useMemo(
    () => state === "ok" && !isOn("DATA_PROCESSING", null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [granted, state],
  )

  return (
    <div className="space-y-6">
      <h1 className="font-display text-3xl tracking-wide text-foreground">Consentimentos</h1>

      {toggleError && <p className="text-sm text-destructive">{toggleError}</p>}

      {state === "loading" && (
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-24 w-full rounded-xl" />
          ))}
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" && (
        <div className="space-y-3">
          {/* COMMUNICATION — master + canais */}
          <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
            <p className="text-sm font-medium text-foreground">
              {CONSENT_TYPE_LABELS.COMMUNICATION}
            </p>
            <p className="text-xs text-muted-foreground">
              Como podemos te avisar sobre seus agendamentos.
            </p>

            <label className="mt-4 flex items-center justify-between gap-3">
              <span className="text-sm text-foreground">Lembretes de agendamento</span>
              <Switch
                checked={isOn("COMMUNICATION", null)}
                onCheckedChange={() => toggle("COMMUNICATION", null)}
              />
            </label>

            <div className="mt-3 space-y-3 border-t border-border pt-3 pl-3">
              {CHANNELS.map((ch) => (
                <label key={ch} className="flex items-center justify-between gap-3">
                  <span className="text-sm text-muted-foreground">
                    {CONSENT_CHANNEL_LABELS[ch]}
                  </span>
                  <Switch
                    checked={isOn("COMMUNICATION", ch)}
                    onCheckedChange={() => toggle("COMMUNICATION", ch)}
                  />
                </label>
              ))}
            </div>
          </section>

          {/* DATA_PROCESSING */}
          <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
            <p className="text-sm font-medium text-foreground">
              {CONSENT_TYPE_LABELS.DATA_PROCESSING}
            </p>
            <p className="text-xs text-muted-foreground">
              Uso de dados pessoais para prestação do serviço.
            </p>
            <label className="mt-4 flex items-center justify-between gap-3">
              <span className="text-sm text-foreground">Autorizar tratamento de dados</span>
              <Switch
                checked={isOn("DATA_PROCESSING", null)}
                onCheckedChange={() => toggle("DATA_PROCESSING", null)}
              />
            </label>
            {dataProcessingOff && (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/5 px-3 py-2.5">
                <AlertTriangle
                  size={14}
                  strokeWidth={1.5}
                  className="mt-0.5 flex-shrink-0 text-amber-600 dark:text-amber-400"
                />
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  Sem o tratamento de dados, alguns serviços podem ficar indisponíveis e seu
                  histórico pode não ser atualizado.
                </p>
              </div>
            )}
          </section>

          {/* PAYMENT_STORAGE */}
          <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
            <p className="text-sm font-medium text-foreground">
              {CONSENT_TYPE_LABELS.PAYMENT_STORAGE}
            </p>
            <label className="mt-4 flex items-center justify-between gap-3">
              <span className="text-sm text-foreground">Salvar cartões para próximas compras</span>
              <Switch
                checked={isOn("PAYMENT_STORAGE", null)}
                onCheckedChange={() => toggle("PAYMENT_STORAGE", null)}
              />
            </label>
          </section>

          {/* MARKETING */}
          <section className="rounded-xl bg-card p-4 ring-1 ring-foreground/10">
            <p className="text-sm font-medium text-foreground">{CONSENT_TYPE_LABELS.MARKETING}</p>
            <p className="text-xs text-muted-foreground">
              Promoções e novidades dos estabelecimentos.
            </p>
            <label className="mt-4 flex items-center justify-between gap-3">
              <span className="text-sm text-foreground">Receber promoções</span>
              <Switch
                checked={isOn("MARKETING", null)}
                onCheckedChange={() => toggle("MARKETING", null)}
              />
            </label>
          </section>
        </div>
      )}
    </div>
  )
}
