"use client"

import { PortalPageHeader } from "@/components/portal/PortalPageHeader"

import { useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import { AlertTriangle, Loader2, LogOut } from "lucide-react"
import { clearPortalToken, portal } from "@/lib/portal-api"
import type { PortalConsentRecord, PortalIdentity } from "@/lib/portal-types"
import { CONSENT_CHANNEL_LABELS, CONSENT_TYPE_LABELS } from "@/lib/constants"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { ErrorState } from "@/components/ErrorState"

type Load = "loading" | "ok" | "error"
type Save = "idle" | "saving" | "saved" | "error"

// Máscara pt-BR: (11) 98123-4567 / (11) 8123-4567
function maskPhone(value: string): string {
  const d = value.replace(/\D/g, "").slice(0, 11)
  if (d.length <= 2) return d.length ? `(${d}` : ""
  if (d.length <= 6) return `(${d.slice(0, 2)}) ${d.slice(2)}`
  if (d.length <= 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
}

interface ProfileUpdateResponse {
  identity_id: string
  name: string | null
  email: string | null
  phone_e164: string
  email_verification_sent: boolean
}

export default function PortalPerfilPage() {
  const router = useRouter()
  const [state, setState] = useState<Load>("loading")
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [phone, setPhone] = useState("")

  const [save, setSave] = useState<Save>("idle")
  const [saveMsg, setSaveMsg] = useState<string | null>(null)

  function load() {
    setState("loading")
    portal
      .get<PortalIdentity>("/portal/identity/me")
      .then((id) => {
        setName(id.name ?? "")
        setEmail(id.email ?? "")
        setPhone(id.phone_national_normalized ? maskPhone(id.phone_national_normalized) : "")
        setState("ok")
      })
      .catch(() => setState("error"))
  }

  useEffect(() => {
    load()
  }, [])

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setSave("saving")
    setSaveMsg(null)
    try {
      const res = await portal.patch<ProfileUpdateResponse>("/portal/profile", {
        name: name || null,
        email: email || null,
        phone: phone ? phone.replace(/\D/g, "") : null,
      })
      setSave("saved")
      setSaveMsg(
        res.email_verification_sent
          ? "Perfil salvo. Enviamos um link para confirmar seu novo e-mail."
          : "Perfil salvo.",
      )
    } catch (err: unknown) {
      const status = (err as { status?: number }).status
      const msg = (err as { message?: string }).message
      setSave("error")
      if (status === 409) {
        setSaveMsg(msg || "Telefone ou e-mail já vinculado a outra conta.")
      } else if (status === 422) {
        setSaveMsg(msg || "Verifique os dados informados (inclua o DDD no telefone).")
      } else {
        setSaveMsg("Não foi possível salvar. Tente novamente.")
      }
    }
  }

  function handleLogout() {
    clearPortalToken()
    router.replace("/portal/login")
  }

  return (
    <div className="space-y-6">
      <PortalPageHeader title="Perfil" />

      {/* Dados pessoais */}
      {state === "loading" && (
        <div className="max-w-lg space-y-4 rounded-xl bg-card p-6 ring-1 ring-foreground/10">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      )}
      {state === "error" && <ErrorState onRetry={load} />}
      {state === "ok" && (
        <form
          onSubmit={handleSave}
          className="max-w-lg space-y-4 rounded-xl bg-card p-6 ring-1 ring-foreground/10"
        >
          <h2 className="text-xl">Dados pessoais</h2>
          <div className="space-y-1.5">
            <Label htmlFor="profile-name">Nome</Label>
            <Input
              id="profile-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="h-10"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-email">E-mail</Label>
            <Input
              id="profile-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="h-10"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="profile-phone">Telefone</Label>
            <Input
              id="profile-phone"
              inputMode="tel"
              value={phone}
              onChange={(e) => setPhone(maskPhone(e.target.value))}
              placeholder="(11) 98123-4567"
              className="h-10"
            />
          </div>

          <div>
            <Button type="submit" disabled={save === "saving"}>
              {save === "saving" ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Salvando…
                </>
              ) : (
                "Salvar alterações"
              )}
            </Button>
            {saveMsg && (
              <p
                className={
                  save === "error"
                    ? "mt-2 text-sm text-destructive"
                    : "mt-2 text-sm text-muted-foreground"
                }
              >
                {saveMsg}
              </p>
            )}
          </div>
        </form>
      )}

      <ConsentsSection />

      {/* Sessão */}
      <div className="max-w-lg rounded-xl bg-card p-6 ring-1 ring-foreground/10">
        <h2 className="text-xl">Sessão</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Encerra sua sessão neste dispositivo.
        </p>
        <Button variant="outline" className="mt-4" onClick={handleLogout}>
          <LogOut size={14} strokeWidth={1.5} /> Sair
        </Button>
      </div>
    </div>
  )
}

/* ============ Consentimentos (transplantado de /portal/consentimentos) ============ */

const CHANNELS = ["WHATSAPP", "EMAIL", "SMS"] as const

// Defaults quando NÃO há registro (espelha consent_service.py):
//   COMMUNICATION → GRANTED (opt-out) · demais → REVOKED (opt-in).
function defaultGranted(type: string): boolean {
  return type === "COMMUNICATION"
}

function key(type: string, channel: string | null): string {
  return `${type}:${channel ?? "*"}`
}

function ConsentsSection() {
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
    <div className="max-w-lg rounded-xl bg-card p-6 ring-1 ring-foreground/10">
      <h2 className="text-xl">Consentimentos</h2>
      <p className="mt-1 text-xs text-muted-foreground">Controle como usamos seus dados.</p>

      {toggleError && <p className="mt-3 text-sm text-destructive">{toggleError}</p>}

      {state === "loading" && (
        <div className="mt-4 space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-lg" />
          ))}
        </div>
      )}
      {state === "error" && (
        <div className="mt-4">
          <ErrorState onRetry={load} />
        </div>
      )}
      {state === "ok" && (
        <div className="mt-4 space-y-3">
          {/* COMMUNICATION — master + canais */}
          <section className="rounded-lg border border-border p-4">
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
          <section className="rounded-lg border border-border p-4">
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
          <section className="rounded-lg border border-border p-4">
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
          <section className="rounded-lg border border-border p-4">
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
