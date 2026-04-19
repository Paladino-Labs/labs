"use client"

import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import type { Service } from "@/types"
import { ActiveBadge } from "@/components/ActiveBadge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog"

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
      alert("Erro ao enviar imagem: " + (err as Error).message)
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
            <textarea
              id="cs-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
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

  // Reset form when dialog opens
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
      alert("Erro ao enviar imagem: " + (err as Error).message)
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
            <textarea
              id="es-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
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

// --- Page ---
export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function fetchServices() {
    try {
      const data = await api.get<Service[]>("/services/?active_only=false")
      setServices(data)
    } catch {
      setError("Erro ao carregar serviços.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchServices() }, [])

  async function toggleActive(service: Service) {
    try {
      await api.patch(`/services/${service.id}`, { active: !service.active })
      fetchServices()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Serviços</h1>
        <CreateServiceDialog onCreated={fetchServices} />
      </div>

      {error && <p className="text-sm text-destructive mb-4">{error}</p>}

      {loading ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : (
        <div className="rounded-md border bg-white">
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
                  <TableCell>{formatBRL(s.price)}</TableCell>
                  <TableCell>{s.duration} min</TableCell>
                  <TableCell><ActiveBadge active={s.active} /></TableCell>
                  <TableCell className="text-right space-x-1">
                    <EditServiceDialog service={s} onUpdated={fetchServices} />
                    <Button size="sm" variant="ghost" onClick={() => toggleActive(s)}>
                      {s.active ? "Desativar" : "Ativar"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
