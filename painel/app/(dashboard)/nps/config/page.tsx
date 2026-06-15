"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { toast } from "sonner"
import { SlidersHorizontal } from "lucide-react"
import { api } from "@/lib/api"
import { COMMUNICATION_CHANNEL_LABELS } from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"

interface NpsConfig {
  id: string
  company_id: string
  enabled: boolean
  channel: string
  delay_minutes: number
  min_interval_days: number
  low_score_threshold: number
  low_score_alert_enabled: boolean
}

// Canais úteis (channel é string livre no backend, mas só WHATSAPP/EMAIL fazem sentido)
const NPS_CHANNELS = ["WHATSAPP", "EMAIL"]

export default function NpsConfigPage() {
  const [cfg, setCfg] = useState<NpsConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setCfg(await api.get<NpsConfig>("/nps/config"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function patch(p: Partial<NpsConfig>) {
    setCfg((c) => (c ? { ...c, ...p } : c))
  }

  async function handleSave() {
    if (!cfg) return
    setSaving(true)
    try {
      const updated = await api.put<NpsConfig>("/nps/config", {
        enabled: cfg.enabled,
        channel: cfg.channel,
        delay_minutes: cfg.delay_minutes,
        min_interval_days: cfg.min_interval_days,
        low_score_threshold: cfg.low_score_threshold,
        low_score_alert_enabled: cfg.low_score_alert_enabled,
      })
      setCfg(updated)
      toast.success("Configuração salva")
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="NPS" title="Configuração" description="Quando e como enviar a pesquisa de satisfação.">
        <Button variant="outline" render={<Link href="/nps" />}>Ver pesquisas</Button>
      </PageHeader>

      {loading ? (
        <Skeleton className="h-96 w-full max-w-2xl" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : cfg ? (
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <SlidersHorizontal className="h-4 w-4" /> Parâmetros gerais
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* enabled */}
            <div className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
              <div>
                <Label htmlFor="nps-enabled">Pesquisa NPS ativa</Label>
                <p className="text-xs text-muted-foreground">
                  Quando ativa, pesquisas são agendadas após cada atendimento concluído.
                </p>
              </div>
              <Switch id="nps-enabled" checked={cfg.enabled} onCheckedChange={(v) => patch({ enabled: v })} />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label>Canal de envio</Label>
                <Select value={cfg.channel} onValueChange={(v) => v && patch({ channel: v })}>
                  <SelectTrigger className="w-full">
                    <SelectValue>{COMMUNICATION_CHANNEL_LABELS[cfg.channel] ?? cfg.channel}</SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    {NPS_CHANNELS.map((c) => (
                      <SelectItem key={c} value={c}>{COMMUNICATION_CHANNEL_LABELS[c] ?? c}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nps-delay">Atraso após conclusão (min)</Label>
                <Input
                  id="nps-delay" type="number" min={0} value={cfg.delay_minutes}
                  onChange={(e) => patch({ delay_minutes: Math.max(0, parseInt(e.target.value, 10) || 0) })}
                />
                <p className="text-xs text-muted-foreground">min. após conclusão do atendimento</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nps-interval">Intervalo mínimo (dias)</Label>
                <Input
                  id="nps-interval" type="number" min={0} value={cfg.min_interval_days}
                  onChange={(e) => patch({ min_interval_days: Math.max(0, parseInt(e.target.value, 10) || 0) })}
                />
                <p className="text-xs text-muted-foreground">dias entre pesquisas para o mesmo cliente</p>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nps-threshold">Limite para nota baixa (0–10)</Label>
                <Input
                  id="nps-threshold" type="number" min={0} max={10} value={cfg.low_score_threshold}
                  onChange={(e) => patch({ low_score_threshold: Math.min(10, Math.max(0, parseInt(e.target.value, 10) || 0)) })}
                />
                <p className="text-xs text-muted-foreground">notas ≤ limite disparam alerta</p>
              </div>
            </div>

            {/* low score alert */}
            <div className="flex items-center justify-between rounded-lg border border-border px-4 py-3">
              <div>
                <Label htmlFor="nps-alert">Alerta de nota baixa</Label>
                <p className="text-xs text-muted-foreground">
                  Notificar gestão quando o cliente avaliar abaixo do limite.
                </p>
              </div>
              <Switch
                id="nps-alert" checked={cfg.low_score_alert_enabled}
                onCheckedChange={(v) => patch({ low_score_alert_enabled: v })}
              />
            </div>

            <div className="flex justify-end">
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Salvando…" : "Salvar"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}
    </div>
  )
}
