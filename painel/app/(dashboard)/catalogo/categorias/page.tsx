"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { toast } from "sonner"
import { Pencil, Trash2 } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import type { Category } from "@/types"
import { PageHeader } from "@/components/PageHeader"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/ErrorState"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogClose, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog"
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select"
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from "@/components/ui/tooltip"

const ENTITY_TYPE_LABELS: Record<string, string> = {
  SERVICE: "Serviço",
  PRODUCT: "Produto",
  EXPENSE: "Despesa",
}

function entityLabel(type: string): string {
  return ENTITY_TYPE_LABELS[type] ?? type.charAt(0) + type.slice(1).toLowerCase()
}

interface FormState {
  name: string
  entity_type: string
  sort_order: string
  is_active: boolean
}

function CategoryFormDialog({
  open,
  onOpenChange,
  initial,
  entityTypes,
  onSubmit,
  saving,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  initial: Category | null
  entityTypes: string[]
  onSubmit: (form: FormState) => void
  saving: boolean
}) {
  const isDefault = initial?.is_default ?? false
  const [form, setForm] = useState<FormState>({
    name: "", entity_type: entityTypes[0] ?? "SERVICE", sort_order: "0", is_active: true,
  })

  useEffect(() => {
    if (open) {
      setForm({
        name: initial?.name ?? "",
        entity_type: initial?.entity_type ?? entityTypes[0] ?? "SERVICE",
        sort_order: String(initial?.sort_order ?? 0),
        is_active: initial?.is_active ?? true,
      })
    }
  }, [open, initial, entityTypes])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{initial ? "Editar categoria" : "Nova categoria"}</DialogTitle>
        </DialogHeader>
        <form
          onSubmit={(e) => { e.preventDefault(); onSubmit(form) }}
          className="space-y-4 py-1"
        >
          <div className="space-y-1">
            <Label htmlFor="cat-name">Nome</Label>
            <Input
              id="cat-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
              disabled={isDefault}
              maxLength={255}
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label>Tipo</Label>
              <Select
                value={form.entity_type}
                onValueChange={(v) => v && setForm((f) => ({ ...f, entity_type: v }))}
                disabled={isDefault}
              >
                <SelectTrigger className="w-full">
                  <SelectValue>{entityLabel(form.entity_type)}</SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {entityTypes.map((t) => (
                    <SelectItem key={t} value={t}>{entityLabel(t)}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="cat-order">Ordem</Label>
              <Input
                id="cat-order"
                type="number"
                value={form.sort_order}
                onChange={(e) => setForm((f) => ({ ...f, sort_order: e.target.value }))}
                disabled={isDefault}
              />
            </div>
          </div>
          <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
            <Label htmlFor="cat-active">Ativa</Label>
            <Switch
              id="cat-active"
              checked={form.is_active}
              onCheckedChange={(v) => setForm((f) => ({ ...f, is_active: v }))}
            />
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="ghost" />}>Cancelar</DialogClose>
            <Button type="submit" disabled={saving || !form.name.trim()}>
              {saving ? "Salvando…" : "Salvar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export default function CategoriasPage() {
  const { role } = useAuth()
  const canManage = role === "OWNER" || role === "ADMIN"

  const [categories, setCategories] = useState<Category[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Category | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<Category | null>(null)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      setCategories(await api.get<Category[]>("/categories/"))
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const entityTypes = useMemo(
    () => Array.from(new Set(categories.map((c) => c.entity_type))),
    [categories],
  )

  const grouped = useMemo(() => {
    const map = new Map<string, Category[]>()
    for (const c of categories) {
      const arr = map.get(c.entity_type) ?? []
      arr.push(c)
      map.set(c.entity_type, arr)
    }
    return Array.from(map.entries()).map(([type, items]) => ({
      type,
      items: [...items].sort((a, b) => a.sort_order - b.sort_order),
    }))
  }, [categories])

  function openCreate() { setEditing(null); setFormOpen(true) }
  function openEdit(cat: Category) { setEditing(cat); setFormOpen(true) }

  async function handleSubmit(form: FormState) {
    setSaving(true)
    try {
      const body = {
        name: form.name.trim(),
        entity_type: form.entity_type,
        sort_order: Number(form.sort_order) || 0,
        is_active: form.is_active,
      }
      if (editing) {
        await api.patch(`/categories/${editing.category_id}`, body)
        toast.success("Categoria atualizada")
      } else {
        await api.post("/categories/", body)
        toast.success("Categoria criada")
      }
      setFormOpen(false)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar categoria")
    } finally {
      setSaving(false)
    }
  }

  async function toggleActive(cat: Category) {
    try {
      await api.patch(`/categories/${cat.category_id}`, { is_active: !cat.is_active })
      setCategories((prev) =>
        prev.map((c) => (c.category_id === cat.category_id ? { ...c, is_active: !c.is_active } : c)),
      )
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao alterar status")
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await api.delete(`/categories/${deleteTarget.category_id}`)
      toast.success("Categoria excluída")
      setDeleteTarget(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao excluir categoria")
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Catálogo"
        title="Categorias"
        description="Agrupe serviços, produtos e despesas por categoria."
      >
        {canManage && <Button onClick={openCreate}>+ Nova categoria</Button>}
      </PageHeader>

      {loading ? (
        <Skeleton className="h-72 w-full" />
      ) : error ? (
        <ErrorState message={error} onRetry={load} />
      ) : categories.length === 0 ? (
        <EmptyState title="Nenhuma categoria" description="Crie a primeira categoria para organizar o catálogo." />
      ) : (
        <div className="space-y-6">
          {grouped.map((group) => (
            <div key={group.type} className="overflow-hidden rounded-lg border border-border bg-card">
              <div className="flex items-center justify-between border-b border-border bg-muted/40 px-4 py-3">
                <span className="font-display text-lg tracking-wide">{entityLabel(group.type)}</span>
                <span className="text-xs text-muted-foreground">{group.items.length} categoria(s)</span>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead className="w-32">Tipo</TableHead>
                    <TableHead className="w-20">Ordem</TableHead>
                    <TableHead className="w-20">Status</TableHead>
                    <TableHead className="w-24">Padrão</TableHead>
                    <TableHead className="w-24 text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {group.items.map((cat) => (
                    <TableRow key={cat.category_id}>
                      <TableCell className="font-medium">{cat.name}</TableCell>
                      <TableCell className="text-muted-foreground">{entityLabel(cat.entity_type)}</TableCell>
                      <TableCell>{cat.sort_order}</TableCell>
                      <TableCell>
                        <Switch
                          checked={cat.is_active}
                          disabled={!canManage}
                          onCheckedChange={() => toggleActive(cat)}
                        />
                      </TableCell>
                      <TableCell>
                        {cat.is_default
                          ? <Badge variant="outline" className="font-normal">Padrão</Badge>
                          : <span className="text-muted-foreground">—</span>}
                      </TableCell>
                      <TableCell className="text-right">
                        {canManage && (
                          cat.is_default ? (
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <div className="flex items-center justify-end gap-2 text-muted-foreground/40">
                                    <Pencil size={15} />
                                    <Trash2 size={15} />
                                  </div>
                                }
                              />
                              <TooltipContent>Categoria padrão</TooltipContent>
                            </Tooltip>
                          ) : (
                            <div className="flex items-center justify-end gap-1">
                              <Button variant="ghost" size="icon-sm" onClick={() => openEdit(cat)}>
                                <Pencil />
                              </Button>
                              <Button
                                variant="ghost"
                                size="icon-sm"
                                className="text-destructive"
                                onClick={() => setDeleteTarget(cat)}
                              >
                                <Trash2 />
                              </Button>
                            </div>
                          )
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ))}
        </div>
      )}

      <CategoryFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        initial={editing}
        entityTypes={entityTypes.length > 0 ? entityTypes : ["SERVICE", "PRODUCT", "EXPENSE"]}
        onSubmit={handleSubmit}
        saving={saving}
      />

      <Dialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir categoria</DialogTitle>
            <DialogDescription>
              Excluir a categoria “{deleteTarget?.name}”? Esta ação não pode ser desfeita.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="ghost" />}>Cancelar</DialogClose>
            <Button variant="destructive" onClick={handleDelete}>Excluir</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
