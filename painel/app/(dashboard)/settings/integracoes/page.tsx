"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { Eye, EyeOff, Info, Smartphone, Timer } from "lucide-react"

// ─── Tipos ───────────────────────────────────────────────────────────────────

type ConnectionStatus = "DISCONNECTED" | "CONNECTING" | "CONNECTED" | "ERROR"

interface ConnectionState {
  status: ConnectionStatus
  phone_number?: string | null
  connected_at?: string | null
  qr_code?: string | null
  qr_expires_in?: number | null
  disconnect_reason?: string | null
}

interface FinancialSettings {
  external_account_id: string | null
  external_account_status: string | null
}

// ─── Constantes ──────────────────────────────────────────────────────────────

const POLL_CONNECTING = 3_000
const POLL_CONNECTED  = 30_000
const POLL_IDLE       = 60_000

// ─── Status Badge WhatsApp ────────────────────────────────────────────────────

function StatusBadge({ status }: { status: ConnectionStatus }) {
  const map: Record<ConnectionStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
    DISCONNECTED: { label: "Desconectado",  variant: "secondary" },
    CONNECTING:   { label: "Conectando…",   variant: "outline" },
    CONNECTED:    { label: "Conectado",      variant: "default" },
    ERROR:        { label: "Erro",           variant: "destructive" },
  }
  const { label, variant } = map[status] ?? map.DISCONNECTED
  return <Badge variant={variant}>{label}</Badge>
}

// ─── Aba WhatsApp ─────────────────────────────────────────────────────────────

function TabWhatsApp() {
  const [conn, setConn] = useState<ConnectionState>({ status: "DISCONNECTED" })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [qrCountdown, setQrCountdown] = useState<number | null>(null)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<ConnectionState>("/whatsapp/connection")
      setConn(data)
      setError(null)
      if (data.qr_expires_in != null && data.qr_expires_in > 0) {
        setQrCountdown(data.qr_expires_in)
      } else if (!data.qr_code) {
        setQrCountdown(null)
      }
    } catch (e: unknown) {
      const status = (e as { status?: number }).status
      if (status !== 404) {
        setError("Não foi possível verificar o status da conexão.")
      }
    }
  }, [])

  useEffect(() => { fetchStatus() }, [fetchStatus])

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)
    const interval =
      conn.status === "CONNECTING" ? POLL_CONNECTING
      : conn.status === "CONNECTED" ? POLL_CONNECTED
      : POLL_IDLE
    pollRef.current = setInterval(fetchStatus, interval)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [conn.status, fetchStatus])

  useEffect(() => {
    if (countdownRef.current) clearInterval(countdownRef.current)
    if (qrCountdown === null || qrCountdown <= 0) return
    countdownRef.current = setInterval(() => {
      setQrCountdown((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(countdownRef.current!)
          setConn((c) => ({ ...c, qr_code: null, qr_expires_in: null }))
          return null
        }
        return prev - 1
      })
    }, 1_000)
    return () => { if (countdownRef.current) clearInterval(countdownRef.current) }
  }, [qrCountdown])

  async function handleConnect() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.post<ConnectionState>("/whatsapp/connection", {})
      setConn(data)
      if (data.qr_expires_in) setQrCountdown(data.qr_expires_in)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao iniciar conexão.")
    } finally {
      setLoading(false)
    }
  }

  async function handleRefreshQR() {
    setLoading(true)
    setError(null)
    try {
      const data = await api.get<{ qr_code: string; expires_in: number }>("/whatsapp/qr")
      setConn((c) => ({ ...c, qr_code: data.qr_code, qr_expires_in: data.expires_in }))
      setQrCountdown(data.expires_in)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao gerar QR Code.")
    } finally {
      setLoading(false)
    }
  }

  async function handleDisconnect() {
    if (!confirm("Deseja realmente desconectar o WhatsApp?")) return
    setLoading(true)
    setError(null)
    try {
      await api.delete("/whatsapp/connection")
      setConn({ status: "DISCONNECTED" })
      setQrCountdown(null)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao desconectar.")
    } finally {
      setLoading(false)
    }
  }

  interface CompanyData {
    settings?: { bot_enabled?: boolean } | null
  }
  const [isBotEnabled, setIsBotEnabled] = useState(false)

  useEffect(() => {
    api.get<CompanyData>("/companies/me")
      .then((d) => {
        setIsBotEnabled(d.settings?.bot_enabled ?? false)
      })
      .catch(() => {})
  }, [])

  async function handleToggleBot() {
    const next = !isBotEnabled
    try {
      await api.patch("/companies/me", { settings: { bot_enabled: next } })
      setIsBotEnabled(next)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao alterar configuração do bot.")
    }
  }

  return (
    <div className="space-y-6">
      {/* WhatsApp Business */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            <Smartphone className="h-4 w-4" /> WhatsApp Business
            <StatusBadge status={conn.status} />
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {error && <p className="text-sm text-destructive">{error}</p>}

          {(conn.status === "DISCONNECTED" || conn.status === "ERROR") && (
            <>
              {conn.disconnect_reason && conn.status === "ERROR" && (
                <p className="text-sm text-muted-foreground">
                  Motivo: {conn.disconnect_reason}
                </p>
              )}
              <p className="text-sm text-muted-foreground">
                Conecte seu WhatsApp para ativar o bot de agendamento automático.
              </p>
              <Button onClick={handleConnect} disabled={loading}>
                {loading ? "Conectando…" : conn.status === "ERROR" ? "Reconectar" : "Conectar WhatsApp"}
              </Button>
            </>
          )}

          {conn.status === "CONNECTING" && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Abra o WhatsApp → <strong>Dispositivos vinculados</strong> → <strong>Vincular dispositivo</strong> e escaneie o QR abaixo.
              </p>
              {conn.qr_code ? (
                <div className="flex flex-col items-center gap-2">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`data:image/png;base64,${conn.qr_code}`}
                    alt="QR Code WhatsApp"
                    className="max-w-[12rem] w-full aspect-square border rounded-lg"
                  />
                  {qrCountdown !== null && qrCountdown > 0 && (
                    <p className="text-xs text-muted-foreground flex items-center gap-1">
                      <Timer className="h-3 w-3" /> Expira em {qrCountdown}s
                    </p>
                  )}
                </div>
              ) : (
                <div className="max-w-[12rem] w-full aspect-square border rounded-lg bg-muted flex items-center justify-center text-sm text-muted-foreground">
                  QR expirado
                </div>
              )}
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={handleRefreshQR} disabled={loading}>
                  Gerar novo QR
                </Button>
                <Button variant="ghost" size="sm" onClick={handleDisconnect} disabled={loading}>
                  Cancelar
                </Button>
              </div>
            </div>
          )}

          {conn.status === "CONNECTED" && (
            <div className="space-y-3">
              <div className="text-sm space-y-1">
                <p>
                  <span className="text-muted-foreground">Número: </span>
                  <span className="font-medium">{conn.phone_number ?? "—"}</span>
                </p>
                {conn.connected_at && (
                  <p>
                    <span className="text-muted-foreground">Conectado desde: </span>
                    <span className="font-medium">{formatDateTime(conn.connected_at)}</span>
                  </p>
                )}
              </div>
              <div className="flex items-center gap-3 pt-1">
                <span className="text-sm text-muted-foreground">Bot de agendamento:</span>
                <button
                  onClick={handleToggleBot}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    isBotEnabled ? "bg-primary" : "bg-muted"
                  }`}
                  aria-label="Toggle bot"
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      isBotEnabled ? "translate-x-6" : "translate-x-1"
                    }`}
                  />
                </button>
                <span className="text-sm font-medium">
                  {isBotEnabled ? "Ativado" : "Desativado"}
                </span>
              </div>
              <Button variant="outline" size="sm" onClick={handleDisconnect} disabled={loading}>
                Desconectar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

// ─── Aba Asaas ────────────────────────────────────────────────────────────────

function TabAsaas() {
  const [settings, setSettings] = useState<FinancialSettings | null>(null)
  const [loadingSettings, setLoadingSettings] = useState(true)
  const [cpfCnpj, setCpfCnpj] = useState("")
  const [birthDate, setBirthDate] = useState("")
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function fetchSettings() {
    setLoadingSettings(true)
    try {
      const data = await api.get<FinancialSettings>("/financial/settings")
      setSettings(data)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao carregar status.")
    } finally {
      setLoadingSettings(false)
    }
  }

  useEffect(() => { fetchSettings() }, [])

  async function handleConfigureAsaas(e: React.FormEvent) {
    e.preventDefault()
    if (!cpfCnpj || !birthDate) return
    setSaving(true)
    setError(null)
    try {
      await api.patch("/companies/me", {
        owner_cpf_cnpj: cpfCnpj.replace(/\D/g, ""),
        owner_birth_date: birthDate,
      })
      await fetchSettings()
      setCpfCnpj("")
      setBirthDate("")
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao configurar subconta.")
    } finally {
      setSaving(false)
    }
  }

  if (loadingSettings) return <p className="text-muted-foreground">Carregando…</p>

  const hasAccount = !!settings?.external_account_id
  const status = settings?.external_account_status

  return (
    <div className="space-y-4">
      {hasAccount && status === "active" && (
        <Card className="border-green-200 bg-green-50">
          <CardContent className="pt-6">
            <p className="font-medium text-green-800">Subconta Asaas ativa</p>
            <p className="text-sm text-green-700 mt-1">
              Sua conta de pagamentos está ativa e pronta para receber cobranças.
            </p>
          </CardContent>
        </Card>
      )}

      {hasAccount && status !== "active" && (
        <Card className="border-yellow-200 bg-yellow-50">
          <CardContent className="pt-6">
            <p className="font-medium text-yellow-800">Subconta em análise/suspensa</p>
            <p className="text-sm text-yellow-700 mt-1">
              Status atual: <span className="font-medium">{status}</span>
            </p>
          </CardContent>
        </Card>
      )}

      {!hasAccount && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Subconta Asaas não configurada</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              Preencha os dados do responsável para criar a subconta de pagamentos.
            </p>

            <form onSubmit={handleConfigureAsaas} className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="asaas-cpfcnpj">CPF ou CNPJ do responsável</Label>
                <Input
                  id="asaas-cpfcnpj"
                  type="text"
                  value={cpfCnpj}
                  onChange={(e) => setCpfCnpj(e.target.value.replace(/\D/g, ""))}
                  placeholder="Somente dígitos"
                  inputMode="numeric"
                />
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="asaas-birthdate">Data de nascimento do responsável</Label>
                <Input
                  id="asaas-birthdate"
                  type="date"
                  value={birthDate}
                  onChange={(e) => setBirthDate(e.target.value)}
                />
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" disabled={saving || !cpfCnpj || !birthDate}>
                {saving ? "Configurando…" : "Configurar subconta Asaas"}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

// ─── Aba PagSeguro ────────────────────────────────────────────────────────────

function TabPagSeguro() {
  const [clientId, setClientId] = useState("")
  const [clientSecret, setClientSecret] = useState("")
  const [showSecret, setShowSecret] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    if (!clientId || !clientSecret) return
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      await api.post("/integrations/credentials", {
        provider: "PAGSEGURO",
        secret: clientSecret,
        config: { client_id: clientId },
      })
      setSaved(true)
      setClientId("")
      setClientSecret("")
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao salvar credenciais.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center justify-between text-base">
            <span className="flex items-center gap-2">
              <Info className="h-4 w-4" /> PagSeguro
            </span>
            <Badge variant="secondary">Sandbox pendente</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Integração com terminais PagSeguro em validação. Configure as credenciais
            abaixo para preparar o ambiente.
          </p>

          <form onSubmit={handleSave} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="psg-client-id">Client ID</Label>
              <Input
                id="psg-client-id"
                type="text"
                value={clientId}
                onChange={(e) => setClientId(e.target.value)}
                placeholder="Client ID"
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="psg-client-secret">Client Secret</Label>
              <div className="relative">
                <Input
                  id="psg-client-secret"
                  type={showSecret ? "text" : "password"}
                  value={clientSecret}
                  onChange={(e) => setClientSecret(e.target.value)}
                  placeholder="Client Secret"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowSecret((v) => !v)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  aria-label={showSecret ? "Ocultar" : "Mostrar"}
                >
                  {showSecret ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
            {saved && <p className="text-sm text-green-700">Credenciais salvas com sucesso.</p>}

            <Button type="submit" disabled={saving || !clientId || !clientSecret}>
              {saving ? "Salvando…" : "Salvar credenciais"}
            </Button>
          </form>

          <p className="text-xs text-muted-foreground">
            Terminal físico aguarda confirmação de endpoint pela equipe PagBank.
            As credenciais serão usadas quando o sandbox for validado.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}

// ─── Página principal ─────────────────────────────────────────────────────────

export default function IntegracoesPage() {
  return (
    <div className="max-w-xl mx-auto space-y-6">
      <h1 className="font-display text-3xl tracking-wide">Integrações</h1>

      <Tabs defaultValue="whatsapp">
        <TabsList>
          <TabsTrigger value="whatsapp">WhatsApp</TabsTrigger>
          <TabsTrigger value="asaas">Asaas</TabsTrigger>
          {/* TabPagSeguro — desabilitado até sandbox PagBank ser validado
          <TabsTrigger value="pagseguro">PagSeguro</TabsTrigger>
          */}
        </TabsList>

        <TabsContent value="whatsapp">
          <TabWhatsApp />
        </TabsContent>

        <TabsContent value="asaas">
          <TabAsaas />
        </TabsContent>

        {/* TabPagSeguro — desabilitado até sandbox PagBank ser validado
        <TabsContent value="pagseguro"><TabPagSeguro /></TabsContent>
        */}
      </Tabs>
    </div>
  )
}
