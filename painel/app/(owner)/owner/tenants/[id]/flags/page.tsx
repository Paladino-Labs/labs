"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { toast } from "sonner"
import { ChevronLeft } from "lucide-react"
import { owner } from "@/lib/owner-api"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { Card, CardContent } from "@/components/ui/card"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"

interface FlagsResponse {
  flags: Record<string, unknown>
}

function isBool(v: unknown): v is boolean {
  return typeof v === "boolean"
}

export default function OwnerTenantFlagsPage() {
  const { id } = useParams<{ id: string }>()

  const [flags, setFlags] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busyKey, setBusyKey] = useState<string | null>(null)

  // Dialog de edição de valor não-booleano
  const [edit, setEdit] = useState<{ key: string; draft: string } | null>(null)
  const [editError, setEditError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const res = await owner.get<FlagsResponse>(`/platform/tenants/${id}/flags`)
      setFlags(res.flags ?? {})
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function putFlag(key: string, value: unknown) {
    const res = await owner.put<FlagsResponse>(`/platform/tenants/${id}/flags/${encodeURIComponent(key)}`, { value })
    setFlags(res.flags ?? {})
  }

  async function handleToggle(key: string, current: boolean) {
    setBusyKey(key)
    // Otimista
    setFlags((prev) => (prev ? { ...prev, [key]: !current } : prev))
    try {
      await putFlag(key, !current)
    } catch (err: unknown) {
      // Reverte em erro
      setFlags((prev) => (prev ? { ...prev, [key]: current } : prev))
      toast.error((err as Error).message ?? "Erro ao atualizar flag")
    } finally {
      setBusyKey(null)
    }
  }

  function openEdit(key: string, value: unknown) {
    setEditError(null)
    setEdit({ key, draft: JSON.stringify(value, null, 2) })
  }

  async function handleSaveEdit() {
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
      await putFlag(edit.key, parsed)
      toast.success("Flag atualizada")
      setEdit(null)
    } catch (err: unknown) {
      setEditError((err as Error).message ?? "Erro ao salvar")
    } finally {
      setSaving(false)
    }
  }

  const entries = flags ? Object.entries(flags) : []

  return (
    <div className="space-y-6">
      <Link
        href={`/owner/tenants/${id}`}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft size={14} strokeWidth={1.5} /> Voltar ao tenant
      </Link>

      <PageHeader
        eyebrow="Plataforma · Tenant"
        title="Feature flags"
        description="Sobrescritas de permissão (permission_overrides) deste tenant."
      />

      {loading ? (
        <Skeleton className="h-64 w-full" />
      ) : error ? (
        <ErrorState
          message={error.includes("404") ? "Config não encontrada." : error}
          onRetry={load}
        />
      ) : entries.length === 0 ? (
        <EmptyState title="Nenhuma flag configurada" description="Este tenant não possui sobrescritas de permissão." />
      ) : (
        <div className="space-y-2">
          {entries.map(([key, value]) => (
            <Card key={key} size="sm">
              <CardContent className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0">
                  <Label className="font-mono text-sm">{key}</Label>
                  {!isBool(value) && (
                    <pre className="mt-1 max-w-full overflow-x-auto rounded-md border border-border bg-muted/40 p-2 text-xs">
                      {JSON.stringify(value, null, 2)}
                    </pre>
                  )}
                </div>
                {isBool(value) ? (
                  <Switch
                    checked={value}
                    disabled={busyKey === key}
                    onCheckedChange={() => handleToggle(key, value)}
                  />
                ) : (
                  <Button size="sm" variant="outline" onClick={() => openEdit(key, value)}>
                    Editar
                  </Button>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Editor JSON para valores não-booleanos */}
      <Dialog open={!!edit} onOpenChange={(v) => { if (!v) setEdit(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="font-mono">{edit?.key}</DialogTitle>
            <DialogDescription>Edite o valor JSON da flag.</DialogDescription>
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
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
