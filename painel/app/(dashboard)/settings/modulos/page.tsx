"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import {
  Boxes, Percent, Gift, RefreshCw, Tag, TrendingUp, Star, ListOrdered,
  MessageSquare, Link2, type LucideIcon,
} from "lucide-react"
import { api } from "@/lib/api"
import {
  MODULE_LABELS, MODULE_DESCRIPTIONS, MODULE_DEPENDENCIES, MODULE_ORDER,
} from "@/lib/constants"
import { PageHeader } from "@/components/PageHeader"
import { ErrorState } from "@/components/ErrorState"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Card, CardContent } from "@/components/ui/card"

interface ModuleActivation {
  activation_id: string
  company_id: string
  module_name: string
  is_active: boolean
}

const MODULE_ICONS: Record<string, LucideIcon> = {
  ESTOQUE: Boxes,
  COMISSOES: Percent,
  PACOTES: Gift,
  ASSINATURAS: RefreshCw,
  PROMOCOES: Tag,
  CRM: TrendingUp,
  NPS: Star,
  FILA: ListOrdered,
  BOT_WHATSAPP: MessageSquare,
  LINK_PUBLICO: Link2,
}

export default function ModulosPage() {
  const [modules, setModules] = useState<ModuleActivation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setModules(await api.get<ModuleActivation[]>("/tenant/modules"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  async function handleToggle(mod: ModuleActivation, next: boolean) {
    setBusy(mod.module_name)
    // Otimista
    setModules((list) => list.map((m) => (m.module_name === mod.module_name ? { ...m, is_active: next } : m)))
    try {
      const action = next ? "activate" : "deactivate"
      await api.post(`/tenant/modules/${mod.module_name}/${action}`, {})
      toast.success(`${MODULE_LABELS[mod.module_name] ?? mod.module_name} ${next ? "ativado" : "desativado"}`)
    } catch (err: unknown) {
      // Rollback
      setModules((list) => list.map((m) => (m.module_name === mod.module_name ? { ...m, is_active: !next } : m)))
      toast.error((err as Error).message ?? "Erro ao alterar módulo")
    } finally {
      setBusy(null)
    }
  }

  // Ordena conforme MODULE_ORDER, mantendo desconhecidos no fim
  const ordered = [...modules].sort((a, b) => {
    const ia = MODULE_ORDER.indexOf(a.module_name as typeof MODULE_ORDER[number])
    const ib = MODULE_ORDER.indexOf(b.module_name as typeof MODULE_ORDER[number])
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib)
  })

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Configurações" title="Módulos" description="Ative funcionalidades adicionais conforme sua operação cresce." />

      {loading ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-32 w-full" />)}
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {ordered.map((m) => {
            const Icon = MODULE_ICONS[m.module_name] ?? Boxes
            const dep = MODULE_DEPENDENCIES[m.module_name]
            return (
              <Card key={m.module_name}>
                <CardContent className="space-y-3 p-5">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-start gap-3 min-w-0">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
                        <Icon className="h-4 w-4" strokeWidth={1.5} />
                      </div>
                      <div className="min-w-0">
                        <p className="[font-family:var(--font-display)] text-lg leading-tight">{MODULE_LABELS[m.module_name] ?? m.module_name}</p>
                        <p className="text-xs text-muted-foreground">{m.is_active ? "Ativo" : "Inativo"}</p>
                      </div>
                    </div>
                    <Switch
                      checked={m.is_active}
                      disabled={busy === m.module_name}
                      onCheckedChange={(v) => handleToggle(m, v)}
                      aria-label={`Alternar ${MODULE_LABELS[m.module_name] ?? m.module_name}`}
                    />
                  </div>
                  <p className="text-sm text-muted-foreground">{MODULE_DESCRIPTIONS[m.module_name] ?? ""}</p>
                  {dep && <p className="text-xs italic text-muted-foreground">↳ {dep}</p>}
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
