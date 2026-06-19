"use client"

import { useCallback, useEffect, useState } from "react"
import { toast } from "sonner"
import { owner } from "@/lib/owner-api"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

interface SettingsResponse {
  settings: Record<string, unknown>
}

export default function OwnerSettingsPage() {
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [edit, setEdit] = useState<{ key: string; draft: string } | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await owner.get<SettingsResponse>("/platform/settings")
      setSettings(res.settings ?? {})
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  function openEdit(key: string, value: unknown) {
    setEditError(null)
    setEdit({ key, draft: JSON.stringify(value, null, 2) })
  }

  async function handleSave() {
    if (!edit) return
    let parsed: unknown
    try {
      parsed = JSON.parse(edit.draft)
    } catch {
      setEditError("JSON inválido.")
      return
    }
    setSaving(true)
    try {
      await owner.put<{ key: string; value: unknown }>(
        `/platform/settings/${encodeURIComponent(edit.key)}`,
        { value: parsed },
      )
      // PUT devolve só a chave alterada → atualiza localmente
      setSettings((prev) => (prev ? { ...prev, [edit.key]: parsed } : prev))
      toast.success("Configuração atualizada")
      setEdit(null)
    } catch (err: unknown) {
      setEditError((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  const entries = settings ? Object.entries(settings) : []

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Plataforma"
        title="Configurações da plataforma"
        description="Dicionário livre de configurações globais."
      />

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : entries.length === 0 ? (
        <EmptyState title="Nenhuma configuração" description="Não há configurações globais definidas." />
      ) : (
        <div className="space-y-2">
          {entries.map(([key, value]) => (
            <Card key={key} size="sm">
              <CardContent className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <Label className="font-mono text-sm">{key}</Label>
                  <pre className="mt-1 max-w-full overflow-x-auto rounded-md border border-border bg-muted/40 p-2 text-xs">
                    {JSON.stringify(value, null, 2)}
                  </pre>
                </div>
                <Button size="sm" variant="outline" onClick={() => openEdit(key, value)}>Editar</Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Dialog open={!!edit} onOpenChange={(v) => { if (!v) setEdit(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-mono">{edit?.key}</DialogTitle>
            <DialogDescription>Edite o valor JSON da configuração.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5 py-1">
            <Textarea
              value={edit?.draft ?? ""}
              onChange={(e) => setEdit((prev) => (prev ? { ...prev, draft: e.target.value } : prev))}
              rows={8}
              className="font-mono text-xs"
            />
            {editError && <p className="text-sm text-destructive">{editError}</p>}
          </div>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button onClick={handleSave} disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
