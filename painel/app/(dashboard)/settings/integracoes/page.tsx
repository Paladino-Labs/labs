"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { WHATSAPP_API_TYPE_LABELS } from "@/lib/constants"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
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
  const [disconnectOpen, setDisconnectOpen] = useState(false)
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
      toast.error((e as Error).message ?? "Erro ao iniciar conexão.")
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
      toast.error((e as Error).message ?? "Erro ao gerar QR Code.")
    } finally {
      setLoading(false)
    }
  }

  // Cancela o fluxo de conexão (sem confirmação — não há vínculo ativo ainda)
  async function handleCancelConnect() {
    setLoading(true)
    try {
      await api.delete("/whatsapp/connection")
      setConn({ status: "DISCONNECTED" })
      setQrCountdown(null)
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao cancelar.")
    } finally {
      setLoading(false)
    }
  }

  async function handleDisconnect() {
    setLoading(true)
    try {
      await api.delete("/whatsapp/connection")
      setConn({ status: "DISCONNECTED" })
      setQrCountdown(null)
      setDisconnectOpen(false)
      toast.success("WhatsApp desconectado")
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao desconectar.")
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
      toast.error((e as Error).message ?? "Erro ao alterar configuração do bot.")
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
                <Button variant="ghost" size="sm" onClick={handleCancelConnect} disabled={loading}>
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
              <Button variant="outline" size="sm" onClick={() => setDisconnectOpen(true)} disabled={loading}>
                Desconectar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <ChannelSettings />

      {/* Confirmação de desconexão */}
      <Dialog open={disconnectOpen} onOpenChange={setDisconnectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Desconectar WhatsApp</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            O bot de agendamento deixará de responder até que você reconecte o número.
          </p>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDisconnect} disabled={loading}>
              Desconectar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ─── Configurações de canal (api type + quiet hours) ────────────────────────────

interface ChannelSettingsState {
  whatsapp_api_type: string
  quiet_hours_enabled: boolean
  quiet_hours_start: string
  quiet_hours_end: string
}

function toHHMM(v: unknown): string {
  if (typeof v !== "string") return ""
  return v.slice(0, 5)
}

function ChannelSettings() {
  const [state, setState] = useState<ChannelSettingsState | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    api.get<Record<string, unknown>>("/communication/settings")
      .then((s) => setState({
        whatsapp_api_type: (s.whatsapp_api_type as string) ?? "UNOFFICIAL_BAILEYS",
        quiet_hours_enabled: (s.quiet_hours_enabled as boolean) ?? true,
        quiet_hours_start: toHHMM(s.quiet_hours_start) || "22:00",
        quiet_hours_end: toHHMM(s.quiet_hours_end) || "08:00",
      }))
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  async function handleSave() {
    if (!state) return
    setSaving(true)
    try {
      await api.put("/communication/settings", {
        whatsapp_api_type: state.whatsapp_api_type,
        quiet_hours_enabled: state.quiet_hours_enabled,
        quiet_hours_start: state.quiet_hours_start,
        quiet_hours_end: state.quiet_hours_end,
      })
      toast.success("Configurações de canal salvas")
    } catch (e: unknown) {
      toast.error((e as Error).message ?? "Erro ao salvar configurações.")
    } finally {
      setSaving(false)
    }
  }

  if (loading || !state) return null

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-base">Configurações de canal</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label>Tipo de API</Label>
          <Select value={state.whatsapp_api_type} onValueChange={(v) => v && setState({ ...state, whatsapp_api_type: v })}>
            <SelectTrigger className="w-full">
              <SelectValue>{WHATSAPP_API_TYPE_LABELS[state.whatsapp_api_type] ?? state.whatsapp_api_type}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {Object.entries(WHATSAPP_API_TYPE_LABELS).map(([k, v]) => <SelectItem key={k} value={k}>{v}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
          <Label htmlFor="qh-enabled">Horário de silêncio</Label>
          <Switch id="qh-enabled" checked={state.quiet_hours_enabled}
            onCheckedChange={(v) => setState({ ...state, quiet_hours_enabled: v })} />
        </div>

        {state.quiet_hours_enabled && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="qh-start">Início silêncio</Label>
              <Input id="qh-start" type="time" value={state.quiet_hours_start}
                onChange={(e) => setState({ ...state, quiet_hours_start: e.target.value })} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="qh-end">Fim silêncio</Label>
              <Input id="qh-end" type="time" value={state.quiet_hours_end}
                onChange={(e) => setState({ ...state, quiet_hours_end: e.target.value })} />
            </div>
          </div>
        )}
        <p className="text-xs text-muted-foreground">Mensagens automáticas dentro desta janela são adiadas.</p>

        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
        </div>
      </CardContent>
    </Card>
  )
}

// ─── Aba Asaas ────────────────────────────────────────────────────────────────

function TabAsaas() {
  const [settings, setSettings] = useState<FinancialSettings | null>(null)
  const [loadingSettings, setLoadingSettings] = useState(true)
  const [cpfCnpj, setCpfCnpj] = useState("")
  const [birthDate, setBirthDate] = useState("")
  const [ownerMobilePhone, setOwnerMobilePhone] = useState("")
  const [ownerIncomeValue, setOwnerIncomeValue] = useState("")
  const [ownerAddress, setOwnerAddress] = useState("")
  const [ownerAddressNumber, setOwnerAddressNumber] = useState("")
  const [ownerProvince, setOwnerProvince] = useState("")
  const [ownerPostalCode, setOwnerPostalCode] = useState("")
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
    setSaving(true)
    setError(null)
    try {
      await api.patch("/companies/me", {
        owner_cpf_cnpj: cpfCnpj.replace(/\D/g, "") || undefined,
        owner_birth_date: birthDate || undefined,
        owner_mobile_phone: ownerMobilePhone || undefined,
        owner_income_value: ownerIncomeValue ? parseFloat(ownerIncomeValue) : undefined,
        owner_address: ownerAddress || undefined,
        owner_address_number: ownerAddressNumber || undefined,
        owner_province: ownerProvince || undefined,
        owner_postal_code: ownerPostalCode || undefined,
      })
      await fetchSettings()
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
          <CardContent className="space-y-6">
            <p className="text-sm text-muted-foreground">
              Preencha os dados do responsável para criar a subconta de pagamentos.
            </p>

            <form onSubmit={handleConfigureAsaas} className="space-y-6">
              {/* Seção: Responsável pela conta */}
              <div className="space-y-3">
                <p className="text-sm font-medium">Responsável pela conta</p>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-cpfcnpj">CPF ou CNPJ</Label>
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
                  <Label htmlFor="asaas-birthdate">Data de nascimento</Label>
                  <Input
                    id="asaas-birthdate"
                    type="date"
                    value={birthDate}
                    onChange={(e) => setBirthDate(e.target.value)}
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-mobile-phone">Celular do responsável</Label>
                  <Input
                    id="asaas-mobile-phone"
                    type="text"
                    value={ownerMobilePhone}
                    onChange={(e) => setOwnerMobilePhone(e.target.value)}
                    placeholder="Ex: 5511999999999 (com DDI e DDD)"
                    inputMode="numeric"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-income">Receita mensal estimada em R$</Label>
                  <Input
                    id="asaas-income"
                    type="number"
                    value={ownerIncomeValue}
                    onChange={(e) => setOwnerIncomeValue(e.target.value)}
                    placeholder="Ex: 5000"
                    min="0"
                  />
                </div>
              </div>

              {/* Seção: Endereço do responsável */}
              <div className="space-y-3">
                <p className="text-sm font-medium">Endereço do responsável</p>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-address">Rua / Logradouro</Label>
                  <Input
                    id="asaas-address"
                    type="text"
                    value={ownerAddress}
                    onChange={(e) => setOwnerAddress(e.target.value)}
                    placeholder="Ex: Rua das Flores"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-address-number">Número</Label>
                  <Input
                    id="asaas-address-number"
                    type="text"
                    value={ownerAddressNumber}
                    onChange={(e) => setOwnerAddressNumber(e.target.value)}
                    placeholder="Ex: 123"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-province">Bairro</Label>
                  <Input
                    id="asaas-province"
                    type="text"
                    value={ownerProvince}
                    onChange={(e) => setOwnerProvince(e.target.value)}
                    placeholder="Ex: Centro"
                  />
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor="asaas-postal-code">CEP</Label>
                  <Input
                    id="asaas-postal-code"
                    type="text"
                    value={ownerPostalCode}
                    onChange={(e) => setOwnerPostalCode(e.target.value.replace(/\D/g, "").slice(0, 8))}
                    placeholder="Ex: 74000000"
                    inputMode="numeric"
                    maxLength={8}
                  />
                </div>
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              <Button type="submit" disabled={saving}>
                {saving ? "Configurando…" : "Configurar subconta Asaas"}
              </Button>
            </form>

            <p className="text-xs text-muted-foreground">
              Esses dados são necessários para criar sua subconta Asaas e processar pagamentos.
              O CEP deve ter 8 dígitos sem traço.
            </p>
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
