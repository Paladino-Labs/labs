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
    // PATCH /companies/me com settings.bot_enabled
    try {
      await api.patch("/companies/me", {
        settings: { bot_enabled: !isBotEnabled },
      })
      setIsBotEnabled((v) => !v)
    } catch (e: unknown) {
      setError((e as Error).message ?? "Erro ao alterar configuração do bot.")
    }
  }

  // bot_enabled vem de /companies/me (carregado separadamente)
  const [isBotEnabled, setIsBotEnabled] = useState(false)
  useEffect(() => {
    if (conn.status !== "CONNECTED") return
    api.get<{ settings?: { bot_enabled?: boolean } }>("/companies/me")
      .then((d) => setIsBotEnabled(d.settings?.bot_enabled ?? false))
      .catch(() => {})
  }, [conn.status])

  // ── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="max-w-xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold">Integrações</h1>

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
