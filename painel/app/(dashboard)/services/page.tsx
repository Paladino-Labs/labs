"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { Clock, Pencil, Trash2, Layers } from "lucide-react"
import { api } from "@/lib/api"
import { useAuth } from "@/hooks/useAuth"
import { formatBRL, formatBRLFromDecimal } from "@/lib/utils"
import type { Service, ServiceVariant } from "@/types"
import { StatusBadge } from "@/components/status-badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"
import {
  Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription,
} from "@/components/ui/sheet"

// --- Create Dialog ---
function CreateServiceDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [duration, setDuration] = useState("")
  const [description, setDescription] = useState("")
  const [imageUrl, setImageUrl] = useState("")
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await api.postForm<{ url: string }>("/uploads/", fd)
      setImageUrl(res.url)
    } catch (err: unknown) {
      toast.error("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post("/services/", {
        name,
        price: parseFloat(price),
        duration: parseInt(duration, 10),
        description: description || undefined,
        image_url: imageUrl || undefined,
      })
      setOpen(false)
      setName(""); setPrice(""); setDuration(""); setDescription(""); setImageUrl("")
      onCreated()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>+ Novo Serviço</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Novo Serviço</DialogTitle></DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="cs-name">Nome *</Label>
            <Input id="cs-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="cs-price">Preço (R$) *</Label>
              <Input id="cs-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required placeholder="50.00" />
            </div>
            <div className="space-y-1">
              <Label htmlFor="cs-duration">Duração (min) *</Label>
              <Input id="cs-duration" type="number" min="1" value={duration}
                onChange={(e) => setDuration(e.target.value)} required placeholder="30" />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="cs-description">Descrição</Label>
            <Textarea
              id="cs-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Descreva o serviço…"
            />
          </div>
          <div className="space-y-1">
            <Label>Imagem</Label>
            {imageUrl && (
              <img src={imageUrl} alt="prévia" className="h-24 w-24 object-cover rounded-md mb-2" />
            )}
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageUpload} />
            <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? "Enviando…" : "Escolher imagem"}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? "Salvando…" : "Criar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- Edit Dialog ---
function EditServiceDialog({ service, onUpdated }: { service: Service; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState(service.name)
  const [price, setPrice] = useState(service.price)
  const [duration, setDuration] = useState(String(service.duration))
  const [description, setDescription] = useState(service.description ?? "")
  const [imageUrl, setImageUrl] = useState(service.image_url ?? "")
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  function handleOpenChange(v: boolean) {
    if (v) {
      setName(service.name)
      setPrice(service.price)
      setDuration(String(service.duration))
      setDescription(service.description ?? "")
      setImageUrl(service.image_url ?? "")
      setError(null)
    }
    setOpen(v)
  }

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await api.postForm<{ url: string }>("/uploads/", fd)
      setImageUrl(res.url)
    } catch (err: unknown) {
      toast.error("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.patch(`/services/${service.id}`, {
        name,
        price: parseFloat(price),
        duration: parseInt(duration, 10),
        description: description || null,
        image_url: imageUrl || null,
      })
      setOpen(false)
      onUpdated()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger render={<Button size="sm" variant="ghost" />}>Editar</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Editar Serviço</DialogTitle></DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="es-name">Nome *</Label>
            <Input id="es-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <Label htmlFor="es-price">Preço (R$) *</Label>
              <Input id="es-price" type="number" min="0" step="0.01" value={price}
                onChange={(e) => setPrice(e.target.value)} required />
            </div>
            <div className="space-y-1">
              <Label htmlFor="es-duration">Duração (min) *</Label>
              <Input id="es-duration" type="number" min="1" value={duration}
                onChange={(e) => setDuration(e.target.value)} required />
            </div>
          </div>
          <div className="space-y-1">
            <Label htmlFor="es-description">Descrição</Label>
            <Textarea
              id="es-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              placeholder="Descreva o serviço…"
            />
          </div>
          <div className="space-y-1">
            <Label>Imagem</Label>
            {imageUrl && (
              <img src={imageUrl} alt="prévia" className="h-24 w-24 object-cover rounded-md mb-2" />
            )}
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleImageUpload} />
            <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
              {uploading ? "Enviando…" : "Trocar imagem"}
            </Button>
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
            <Button type="submit" disabled={saving}>{saving ? "Salvando…" : "Salvar"}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// --- Variants Sheet ---
function VariantsSheet({
  service,
  onClose,
  onCountChange,
}: {
  service: Service | null
  onClose: () => void
  onCountChange: (serviceId: string, count: number) => void
}) {
  const [variants, setVariants] = useState<ServiceVariant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [duration, setDuration] = useState("")
  const [sortOrder, setSortOrder] = useState("")
  const [adding, setAdding] = useState(false)

  const [editing, setEditing] = useState<ServiceVariant | null>(null)

  const serviceId = service?.id ?? null

  const load = useCallback(async () => {
    if (!serviceId) return
    setLoading(true); setError(null)
    try {
      const data = await api.get<ServiceVariant[]>(`/services/${serviceId}/variants`)
      setVariants(data)
      onCountChange(serviceId, data.filter((v) => v.is_active).length)
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [serviceId, onCountChange])

  useEffect(() => {
    if (serviceId) {
      setName(""); setPrice(""); setDuration(""); setSortOrder(String(variants.length))
      load()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceId])

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    if (!serviceId) return
    setAdding(true)
    try {
      await api.post(`/services/${serviceId}/variants`, {
        name: name.trim(),
        price: parseFloat(price),
        duration_min: parseInt(duration, 10),
        sort_order: Number(sortOrder) || 0,
      })
      toast.success("Variante criada")
      setName(""); setPrice(""); setDuration(""); setSortOrder("")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao criar variante")
    } finally {
      setAdding(false)
    }
  }

  async function handleSaveEdit() {
    if (!serviceId || !editing) return
    try {
      await api.patch(`/services/${serviceId}/variants/${editing.variant_id}`, {
        name: editing.name.trim(),
        price: parseFloat(editing.price),
        duration_min: editing.duration_min,
        is_active: editing.is_active,
      })
      toast.success("Variante atualizada")
      setEditing(null)
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao salvar variante")
    }
  }

  async function handleDelete(variant: ServiceVariant) {
    if (!serviceId) return
    if (!confirm(`Excluir a variante "${variant.name}"?`)) return
    try {
      await api.delete(`/services/${serviceId}/variants/${variant.variant_id}`)
      toast.success("Variante excluída")
      load()
    } catch (err: unknown) {
      toast.error((err as Error).message ?? "Erro ao excluir variante")
    }
  }

  return (
    <Sheet open={!!service} onOpenChange={(v) => !v && onClose()}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Variantes</SheetTitle>
          <SheetDescription>{service?.name}</SheetDescription>
        </SheetHeader>

        <div className="rounded-lg border border-border bg-card">
          {loading ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Carregando…</p>
          ) : error ? (
            <p className="px-4 py-6 text-sm text-destructive">{error}</p>
          ) : variants.length === 0 ? (
            <p className="px-4 py-6 text-sm text-muted-foreground">Nenhuma variante cadastrada.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead className="text-right">Preço</TableHead>
                  <TableHead className="text-right">Duração</TableHead>
                  <TableHead className="text-right">Ordem</TableHead>
                  <TableHead className="w-20 text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {variants.map((v) => (
                  <TableRow key={v.variant_id} className={v.is_active ? "" : "opacity-50"}>
                    <TableCell className="font-medium">{v.name}</TableCell>
                    <TableCell className="text-right">{formatBRLFromDecimal(v.price)}</TableCell>
                    <TableCell className="text-right">{v.duration_min} min</TableCell>
                    <TableCell className="text-right">{v.sort_order}</TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button variant="ghost" size="icon-sm" onClick={() => setEditing(v)}>
                          <Pencil />
                        </Button>
                        <Button variant="ghost" size="icon-sm" className="text-destructive" onClick={() => handleDelete(v)}>
                          <Trash2 />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {editing ? (
          <div className="rounded-lg border border-border bg-card p-4 space-y-3">
            <p className="font-display text-lg tracking-wide">Editar variante</p>
            <div className="space-y-1">
              <Label htmlFor="ev-name">Nome</Label>
              <Input id="ev-name" value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="ev-price">Preço (decimal)</Label>
                <Input id="ev-price" type="number" min="0" step="0.01" value={editing.price}
                  onChange={(e) => setEditing({ ...editing, price: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="ev-duration">Duração (min)</Label>
                <Input id="ev-duration" type="number" min="1" value={editing.duration_min}
                  onChange={(e) => setEditing({ ...editing, duration_min: parseInt(e.target.value, 10) || 0 })} />
              </div>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border px-3 py-2">
              <Label htmlFor="ev-active">Ativa</Label>
              <input id="ev-active" type="checkbox" checked={editing.is_active}
                onChange={(e) => setEditing({ ...editing, is_active: e.target.checked })}
                className="h-4 w-4 accent-primary cursor-pointer" />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setEditing(null)}>Cancelar</Button>
              <Button onClick={handleSaveEdit}>Salvar</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleAdd} className="rounded-lg border border-border bg-card p-4 space-y-3">
            <p className="font-display text-lg tracking-wide">Nova variante</p>
            <div className="space-y-1">
              <Label htmlFor="nv-name">Nome</Label>
              <Input id="nv-name" value={name} onChange={(e) => setName(e.target.value)} required />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="nv-price">Preço (decimal)</Label>
                <Input id="nv-price" type="number" min="0" step="0.01" placeholder="0.00"
                  value={price} onChange={(e) => setPrice(e.target.value)} required />
              </div>
              <div className="space-y-1">
                <Label htmlFor="nv-duration">Duração (min)</Label>
                <Input id="nv-duration" type="number" min="1"
                  value={duration} onChange={(e) => setDuration(e.target.value)} required />
              </div>
            </div>
            <div className="space-y-1">
              <Label htmlFor="nv-order">Ordem</Label>
              <Input id="nv-order" type="number" value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value)} />
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={adding}>{adding ? "Adicionando…" : "+ Adicionar"}</Button>
            </div>
          </form>
        )}
      </SheetContent>
    </Sheet>
  )
}

// --- Page ---
export default function ServicesPage() {
  const { role } = useAuth()
  const canManage = role === "OWNER" || role === "ADMIN"

  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [variantCounts, setVariantCounts] = useState<Record<string, number>>({})
  const [variantsService, setVariantsService] = useState<Service | null>(null)

  const fetchServices = useCallback(async () => {
    try {
      const data = await api.get<Service[]>("/services/?active_only=false")
      setServices(data)
      if (canManage) {
        // contadores de variantes ativas por serviço (catálogo pequeno)
        const entries = await Promise.all(
          data.map(async (s) => {
            try {
              const vs = await api.get<ServiceVariant[]>(`/services/${s.id}/variants`)
              return [s.id, vs.filter((v) => v.is_active).length] as const
            } catch {
              return [s.id, 0] as const
            }
          }),
        )
        setVariantCounts(Object.fromEntries(entries))
      }
    } catch {
      setError("Erro ao carregar serviços.")
    } finally {
      setLoading(false)
    }
  }, [canManage])

  useEffect(() => { fetchServices() }, [fetchServices])

  const handleCountChange = useCallback((serviceId: string, count: number) => {
    setVariantCounts((prev) => ({ ...prev, [serviceId]: count }))
  }, [])

  async function toggleActive(service: Service) {
    try {
      await api.patch(`/services/${service.id}`, { active: !service.active })
      fetchServices()
    } catch (err: unknown) {
      toast.error((err as Error).message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-3xl tracking-wide">Serviços</h1>
        {canManage && <CreateServiceDialog onCreated={fetchServices} />}
      </div>

      {error && <p className="text-sm text-destructive mb-4">{error}</p>}

      {loading ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Imagem</TableHead>
                <TableHead>Nome</TableHead>
                <TableHead>Preço</TableHead>
                <TableHead>Duração</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {services.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                    Nenhum serviço cadastrado.
                  </TableCell>
                </TableRow>
              )}
              {services.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    {s.image_url ? (
                      <img src={s.image_url} alt={s.name} className="h-10 w-10 object-cover rounded-md" />
                    ) : (
                      <div className="h-10 w-10 rounded-md bg-muted flex items-center justify-center text-muted-foreground text-xs">
                        —
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="font-medium">
                    <div>{s.name}</div>
                    {s.description && (
                      <div className="text-xs text-muted-foreground mt-0.5 max-w-xs truncate">{s.description}</div>
                    )}
                  </TableCell>
                  <TableCell>
                    <span className="[font-family:var(--font-display)] text-lg text-foreground">{formatBRL(s.price)}</span>
                  </TableCell>
                  <TableCell>
                    <span className="inline-flex items-center gap-1 text-sm">
                      <Clock className="h-3 w-3 text-muted-foreground" />{s.duration} min
                    </span>
                  </TableCell>
                  <TableCell><StatusBadge active={s.active} /></TableCell>
                  <TableCell className="text-right space-x-1">
                    {canManage && (
                      <Button size="sm" variant="outline" onClick={() => setVariantsService(s)}>
                        <Layers className="h-3.5 w-3.5" />
                        {variantCounts[s.id] ? `Variantes (${variantCounts[s.id]})` : "Variantes"}
                      </Button>
                    )}
                    {canManage && <EditServiceDialog service={s} onUpdated={fetchServices} />}
                    {canManage && (
                      <Button size="sm" variant="ghost" onClick={() => toggleActive(s)}>
                        {s.active ? "Desativar" : "Ativar"}
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <VariantsSheet
        service={variantsService}
        onClose={() => setVariantsService(null)}
        onCountChange={handleCountChange}
      />
    </div>
  )
}
