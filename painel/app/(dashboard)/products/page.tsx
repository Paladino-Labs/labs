"use client"

import { useEffect, useRef, useState } from "react"
import { toast } from "sonner"
import { ImagePlus, Loader2, X } from "lucide-react"
import { api } from "@/lib/api"
import { formatBRL, cn } from "@/lib/utils"
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

// --- Image gallery (slot 1 = primária persiste em image_url; 2–5 "Em breve") ---
function ImageGalleryField({
  value,
  onChange,
  label = "Galeria de imagens",
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
      toast.error("Erro ao enviar imagem: " + (err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ""
    }
  }

  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleFile} />
      <div className="grid grid-cols-5 gap-2">
        {/* Slot 1 — primária */}
        <div className="space-y-1">
          <button
            type="button"
            onClick={() => !uploading && fileRef.current?.click()}
            className={cn(
              "relative flex aspect-square w-full items-center justify-center overflow-hidden rounded-lg border border-border bg-muted/30 transition-colors hover:bg-muted",
            )}
          >
            {uploading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : value ? (
              <>
                <img src={value} alt="primária" className="h-full w-full object-cover" />
                <span
                  role="button"
                  tabIndex={0}
                  onClick={(e) => { e.stopPropagation(); onChange("") }}
                  className="absolute right-1 top-1 flex h-5 w-5 items-center justify-center rounded-full bg-background/90 text-foreground shadow-sm hover:bg-background"
                >
                  <X className="h-3 w-3" />
                </span>
              </>
            ) : (
              <ImagePlus className="h-5 w-5 text-muted-foreground" />
            )}
          </button>
          <p className="text-center text-[10px] uppercase tracking-wide text-muted-foreground">Primária</p>
        </div>
        {/* Slots 2–5 — Em breve */}
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="space-y-1">
            <div className="flex aspect-square w-full items-center justify-center rounded-lg border border-dashed border-border bg-muted/20 opacity-60">
              <ImagePlus className="h-4 w-4 text-muted-foreground/50" />
            </div>
            <p className="text-center text-[10px] text-muted-foreground/60">Em breve</p>
          </div>
        ))}
      </div>
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
          <ImageGalleryField value={imageUrl} onChange={setImageUrl} />
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
  const [stock, setStock] = useState(String(product.stock))
  const [description, setDescription] = useState(product.description ?? "")
  const [imageUrl, setImageUrl] = useState(product.image_url ?? "")

  function handleOpenChange(v: boolean) {
    if (v) {
      setName(product.name)
      setPrice(product.price)
      setStock(String(product.stock))
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
        stock: parseInt(stock, 10),
        description: description || null,
        image_url: imageUrl || null,
      })
      setOpen(false)
      onUpdated()
    } catch (err: unknown) {
      const e = err as { message?: string; status?: number }
      if (e.status === 422) {
        setError("Estoque não pode ser negativo")
      } else {
        setError(e.message ?? "Erro desconhecido")
      }
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
            <Label htmlFor="ep-stock">Estoque</Label>
            <Input
              id="ep-stock"
              type="number"
              min="0"
              step="1"
              value={stock}
              onChange={(e) => setStock(e.target.value)}
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
          <ImageGalleryField value={imageUrl} onChange={setImageUrl} />
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
        <h1 className="font-display text-3xl tracking-wide">Produtos</h1>
        <CreateProductDialog onCreated={fetchProducts} />
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
                <TableHead>Estoque</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {products.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
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
                  <TableCell>{p.stock}</TableCell>
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
