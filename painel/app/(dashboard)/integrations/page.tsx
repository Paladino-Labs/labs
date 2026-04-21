"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { formatDateTime } from "@/lib/utils"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

// ─── Tipos ──────────────────────────────────────────────────────────────────

type ConnectionStatus = "DISCONNECTED" | "CONNECTING" | "CONNECTED" | "ERROR"

interface ConnectionState {
  status: ConnectionStatus
  phone_number?: string | null
  connected_at?: string | null
  qr_code?: string | null
  qr_expires_in?: number | null
  disconnect_reason?: string | null
}

// ─── Constantes ─────────────────────────────────────────────────────────────

const POLL_CONNECTING = 3_000   // 3s enquanto aguarda scan
const POLL_CONNECTED  = 30_000  // 30s verificação de saúde
const POLL_IDLE       = 60_000  // 60s quando desconectado

// ─── Componente de Status Badge ─────────────────────────────────────────────

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

// ─── Componente principal ────────────────────────────────────────────────────

export default function IntegrationsPage() {
  const [conn, setConn] = useState<ConnectionState>({ status: "DISCONNECTED" })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Countdown local do QR (decrementado a cada segundo sem poll extra)
  const [qrCountdown, setQrCountdown] = useState<number | null>(null)
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ── Fetch do estado ─────────────────────────────────────────────────────

  const fetchStatus = useCallback(async () => {
    try {
      const data = await api.get<ConnectionState>("/whatsapp/connection")
      setConn(data)
      setError(null)

      // Atualiza countdown do QR quando vem um novo qr_expires_in
      if (data.qr_expires_in != null && data.qr_expires_in > 0) {
        setQrCountdown(data.qr_expires_in)
      } else if (!data.qr_code) {
        setQrCountdown(null)
      }
    } catch (e: unknown) {
      const status = (e as { status?: number }).status
      // 404 = empresa sem registro ainda → trata como DISCONNECTED
      if (status !== 404) {
        setError("Não foi possível verificar o status da conexão.")
      }
    }
  }, [])

  // ── Polling adaptativo ──────────────────────────────────────────────────

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  useEffect(() => {
    if (pollRef.current) clearInterval(pollRef.current)

    const interval =
      conn.status === "CONNECTING" ? POLL_CONNECTING
      : conn.status === "CONNECTED" ? POLL_CONNECTED
      : POLL_IDLE

    pollRef.current = setInterval(fetchStatus, interval)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [conn.status, fetchStatus])

  // ── Countdown local do QR ───────────────────────────────────────────────

  useEffect(() => {
    if (countdownRef.current) clearInterval(countdownRef.current)
    if (qrCountdown === null || qrCountdown <= 0) return

    countdownRef.current = setInterval(() => {
      setQrCountdown((prev) => {
        if (prev === null || prev <= 1) {
          clearInterval(countdownRef.current!)
          // QR expirou — limpa para exibir botão "Gerar novo QR"
          setConn((c) => ({ ...c, qr_code: null, qr_expires_in: null }))
          return null
        }
        return prev - 1
      })
    }, 1_000)

    return () => { if (countdownRef.current) clearInterval(countdownRef.current) }
  }, [qrCountdown])

  // ── Ações ────────────────────────────────────────────────────────────────

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

  async function handleToggleBot() {
    const next = !isBotEnabled
    try {
      await api.patch("/companies/me", { settings: { bot_enabled: next } })
      setIsBotEnabled(next)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao alterar configuração do bot.")
    }
  }

  // Dados da empresa (bot_enabled + online_booking_enabled + slug)
  interface CompanyData {
    name: string
    slug?: string | null
    settings?: {
      bot_enabled?: boolean
      online_booking_enabled?: boolean
    } | null
  }
  const [company, setCompany] = useState<CompanyData | null>(null)
  const [isBotEnabled, setIsBotEnabled] = useState(false)
  const [isOnlineBookingEnabled, setIsOnlineBookingEnabled] = useState(false)
  const [slugInput, setSlugInput] = useState("")
  const [savingSlug, setSavingSlug] = useState(false)
  const [copied, setCopied] = useState(false)
  // URL vinda do backend — fonte única de verdade (BOOKING_BASE_URL no .env do servidor)
  const [bookingUrl, setBookingUrl] = useState<string | null>(null)

  useEffect(() => {
    api.get<CompanyData>("/companies/me")
      .then((d) => {
        setCompany(d)
        setIsBotEnabled(d.settings?.bot_enabled ?? false)
        setIsOnlineBookingEnabled(d.settings?.online_booking_enabled ?? false)
        setSlugInput(d.slug ?? "")

        // Busca o booking_url real do backend (evita depender de NEXT_PUBLIC_FRONTEND_URL)
        if (d.slug) {
          api.get<{ booking_url: string }>(`/booking/${d.slug}/info`)
            .then((info) => setBookingUrl(info.booking_url))
            .catch(() => {})
        }
      })
      .catch(() => {})
  }, [])

  async function handleSaveSlug() {
    if (!slugInput.trim()) return
    setSavingSlug(true)
    try {
      const newSlug = slugInput.trim()
      await api.patch("/companies/me", { company: { slug: newSlug } })
      setCompany((c) => c ? { ...c, slug: newSlug } : c)

      // Atualiza booking_url com o novo slug
      api.get<{ booking_url: string }>(`/booking/${newSlug}/info`)
        .then((info) => setBookingUrl(info.booking_url))
        .catch(() => {})
    } catch (e: unknown) {
      alert((e as Error).message)
    } finally {
      setSavingSlug(false)
    }
  }

  async function handleToggleOnlineBooking() {
    const next = !isOnlineBookingEnabled
    try {
      await api.patch("/companies/me", { settings: { online_booking_enabled: next } })
      setIsOnlineBookingEnabled(next)
    } catch (e: unknown) {
      alert((e as Error).message)
    }
  }

  function handleCopyLink() {
    if (!bookingUrl) return
    navigator.clipboard.writeText(bookingUrl)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Integrações</h1>

      {/* ── Agendamento Online ── */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">🔗 Agendamento Online</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Slug */}
          <div className="space-y-1">
            <p className="text-sm text-muted-foreground">
              Link personalizado da sua empresa (somente letras, números e hífen).
            </p>
            <div className="flex gap-2">
              <input
                type="text"
                value={slugInput}
                onChange={(e) => setSlugInput(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                placeholder="minha-barbearia"
                className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
              />
              <Button
                size="sm"
                onClick={handleSaveSlug}
                disabled={savingSlug || !slugInput.trim() || slugInput === company?.slug}
              >
                {savingSlug ? "Salvando…" : "Salvar"}
              </Button>
            </div>
          </div>

          {/* Toggle */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-muted-foreground">Agendamento online:</span>
            <button
              onClick={handleToggleOnlineBooking}
              disabled={!company?.slug}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors disabled:opacity-40 ${
                isOnlineBookingEnabled ? "bg-primary" : "bg-muted"
              }`}
              aria-label="Toggle online booking"
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                  isOnlineBookingEnabled ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
            <span className="text-sm font-medium">
              {isOnlineBookingEnabled ? "Ativado" : "Desativado"}
            </span>
          </div>
          {!company?.slug && (
            <p className="text-xs text-muted-foreground">
              Configure o link personalizado acima para ativar o agendamento online.
            </p>
          )}

          {/* URL */}
          {bookingUrl && isOnlineBookingEnabled && (
            <div className="rounded-lg bg-muted px-3 py-2 text-sm break-all flex items-center justify-between gap-2">
              <span className="text-muted-foreground font-mono text-xs">{bookingUrl}</span>
              <Button size="sm" variant="outline" onClick={handleCopyLink}>
                {copied ? "✓ Copiado" : "Copiar"}
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-base flex items-center gap-2">
            📱 WhatsApp Business
            <StatusBadge status={conn.status} />
          </CardTitle>
        </CardHeader>

        <CardContent className="space-y-4">
          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          {/* ── DISCONNECTED / ERROR ── */}
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

          {/* ── CONNECTING ── */}
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
                    className="w-48 h-48 border rounded-lg"
                  />
                  {qrCountdown !== null && qrCountdown > 0 && (
                    <p className="text-xs text-muted-foreground">
                      ⏱ Expira em {qrCountdown}s
                    </p>
                  )}
                </div>
              ) : (
                <div className="w-48 h-48 border rounded-lg bg-muted flex items-center justify-center text-sm text-muted-foreground">
                  QR expirado
                </div>
              )}

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRefreshQR}
                  disabled={loading}
                >
                  Gerar novo QR
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDisconnect}
                  disabled={loading}
                >
                  Cancelar
                </Button>
              </div>
            </div>
          )}

          {/* ── CONNECTED ── */}
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
                    <span className="font-medium">
                      {formatDateTime(conn.connected_at)}
                    </span>
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

              <Button
                variant="outline"
                size="sm"
                onClick={handleDisconnect}
                disabled={loading}
              >
                Desconectar
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
