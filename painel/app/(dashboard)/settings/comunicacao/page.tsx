"use client"

import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { AlertTriangle, Lock } from "lucide-react"

interface CommunicationSettings {
  whatsapp_enabled: boolean
  email_enabled: boolean
  [key: string]: unknown
}

function AccessRestricted() {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20 text-center text-muted-foreground">
      <Lock className="h-8 w-8 opacity-40" />
      <p className="text-base font-medium">Acesso restrito</p>
      <p className="text-sm">Esta página está disponível apenas para OWNER e ADMIN.</p>
    </div>
  )
}

function Toggle({
  enabled,
  onChange,
  label,
  ariaLabel,
}: {
  enabled: boolean
  onChange: () => void
  label: string
  ariaLabel: string
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm text-muted-foreground">{label}</span>
      <button
        onClick={onChange}
        aria-label={ariaLabel}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
          enabled ? "bg-primary" : "bg-muted"
        }`}
      >
        <span
          className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
            enabled ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
      <span className="text-sm font-medium">{enabled ? "Habilitado" : "Desabilitado"}</span>
    </div>
  )
}

export default function ComunicacaoPage() {
  const { role } = useAuth()
  const [settings, setSettings] = useState<CommunicationSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)

  const canAccess = role === "OWNER" || role === "ADMIN"

  useEffect(() => {
    if (!canAccess) return
    api
      .get<CommunicationSettings>("/communication/settings")
      .then(setSettings)
      .catch((e: unknown) => setError((e as Error).message ?? "Erro ao carregar configurações"))
      .finally(() => setLoading(false))
  }, [canAccess])

  if (!canAccess) return <AccessRestricted />
  if (loading)    return <p className="text-muted-foreground">Carregando…</p>
  if (error)      return <p className="text-destructive">{error}</p>
  if (!settings)  return null

  async function handleToggle(field: "whatsapp_enabled" | "email_enabled") {
    if (!settings) return
    const next = !settings[field]
    const prev = { ...settings }
    setSettings({ ...settings, [field]: next })
    setSaveError(null)
    try {
      await api.put<CommunicationSettings>("/communication/settings", { [field]: next })
    } catch (e: unknown) {
      setSettings(prev)
      setSaveError((e as Error).message ?? "Erro ao salvar configuração")
    }
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="[font-family:var(--font-display)] text-3xl tracking-wide">Comunicação</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Gerencie os canais de notificação da sua empresa.
        </p>
      </div>

      {saveError && (
        <p className="text-sm text-destructive">{saveError}</p>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Canais de comunicação</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {/* WhatsApp */}
          <div className="space-y-1">
            <Toggle
              enabled={settings.whatsapp_enabled}
              onChange={() => handleToggle("whatsapp_enabled")}
              label="WhatsApp habilitado"
              ariaLabel="Toggle WhatsApp"
            />
          </div>

          {/* Email */}
          <div className="space-y-1">
            <Toggle
              enabled={settings.email_enabled}
              onChange={() => handleToggle("email_enabled")}
              label="Email habilitado"
              ariaLabel="Toggle email"
            />
            {!settings.email_enabled && (
              <p className="flex items-center gap-1 text-xs text-muted-foreground pt-1">
                <AlertTriangle className="h-3 w-3 shrink-0" />
                Recuperação de senha e convites não serão enviados por email.
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
