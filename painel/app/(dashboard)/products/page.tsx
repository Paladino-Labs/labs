"use client"

import { useEffect, useRef, useState } from "react"
import { api } from "@/lib/api"
import { formatBRL } from "@/lib/utils"
import type { Product } from "@/types"
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

// --- Shared image upload ---
function ImageUploadField({
  value,
  onChange,
  label = "Imagem",
}: {
  value: string
  onChange: (url: string) => void
  label?: string
}) {
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  async function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await api.postForm<{ url: string }>("/uploads/", fd)
      onChange(res.url)
    } catch (err: unknown) {
      alert("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      {value && (
        <img src={value} alt="prévia" className="h-24 w-24 object-cover rounded-md mb-2" />
      )}
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
      <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()} disabled={uploading}>
        {uploading ? "Enviando…" : value ? "Trocar imagem" : "Escolher imagem"}
      </Button>
    </div>
  )
}

// --- Create Dialog ---
function CreateProductDialog({ onCreated }: { onCreated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [description, setDescription] = useState("")
  const [imageUrl, setImageUrl] = useState("")

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post("/products/", {
        name,
        price: parseFloat(price),
        description: description || undefined,
        image_url: imageUrl || undefined,
      })
      setOpen(false)
      setName(""); setPrice(""); setDescription(""); setImageUrl("")
      onCreated()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button />}>+ Novo Produto</DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Novo Produto</DialogTitle></DialogHeader>
        <form onSubmit={handleCreate} className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="cp-name">Nome *</Label>
            <Input id="cp-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cp-price">Preço (R$) *</Label>
            <Input
              id="cp-price"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
              placeholder="25.00"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="cp-desc">Descrição</Label>
            <textarea
              id="cp-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              placeholder="Descreva o produto…"
            />
          </div>
          <ImageUploadField value={imageUrl} onChange={setImageUrl} />
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
function EditProductDialog({ product, onUpdated }: { product: Product; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState(product.name)
  const [price, setPrice] = useState(product.price)
  const [description, setDescription] = useState(product.description ?? "")
  const [imageUrl, setImageUrl] = useState(product.image_url ?? "")

  function handleOpenChange(v: boolean) {
    if (v) {
      setName(product.name)
      setPrice(product.price)
      setDescription(product.description ?? "")
      setImageUrl(product.image_url ?? "")
      setError(null)
    }
    setOpen(v)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.patch(`/products/${product.id}`, {
        name,
        price: parseFloat(price),
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
        <DialogHeader><DialogTitle>Editar Produto</DialogTitle></DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="ep-name">Nome *</Label>
            <Input id="ep-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ep-price">Preço (R$) *</Label>
            <Input
              id="ep-price"
              type="number"
              min="0"
              step="0.01"
              value={price}
              onChange={(e) => setPrice(e.target.value)}
              required
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ep-desc">Descrição</Label>
            <textarea
              id="ep-desc"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
              placeholder="Descreva o produto…"
            />
          </div>
          <ImageUploadField value={imageUrl} onChange={setImageUrl} />
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
export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function fetchProducts() {
    try {
      const data = await api.get<Product[]>("/products/?active_only=false")
      setProducts(data)
    } catch {
      setError("Erro ao carregar produtos.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProducts() }, [])

  async function toggleActive(product: Product) {
    try {
      await api.patch(`/products/${product.id}`, { active: !product.active })
      fetchProducts()
    } catch (err: unknown) {
      alert((err as Error).message)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Produtos</h1>
        <CreateProductDialog onCreated={fetchProducts} />
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
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    Nenhum produto cadastrado.
                  </TableCell>
                </TableRow>
              )}
              {products.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>
                    {p.image_url ? (
                      <img src={p.image_url} alt={p.name} className="h-10 w-10 object-cover rounded-md" />
                    ) : (
                      <div className="h-10 w-10 rounded-md bg-muted flex items-center justify-center text-muted-foreground text-xs">
                        —
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="font-medium">
                    <div>{p.name}</div>
                    {p.description && (
                      <div className="text-xs text-muted-foreground mt-0.5 max-w-xs truncate">{p.description}</div>
                    )}
                  </TableCell>
                  <TableCell>{formatBRL(p.price)}</TableCell>
                  <TableCell><ActiveBadge active={p.active} /></TableCell>
                  <TableCell className="text-right space-x-1">
                    <EditProductDialog product={p} onUpdated={fetchProducts} />
                    <Button size="sm" variant="ghost" onClick={() => toggleActive(p)}>
                      {p.active ? "Desativar" : "Ativar"}
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
