"use client"

import { useEffect, useState } from "react"
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

export default function ServicesPage() {
  const [services, setServices] = useState<Service[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState("")
  const [price, setPrice] = useState("")
  const [duration, setDuration] = useState("")

  async function fetchServices() {
    try {
      const data = await api.get<Service[]>("/services/")
      setServices(data)
    } catch {
      setError("Erro ao carregar serviços.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchServices() }, [])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post("/services/", {
        name,
        price: parseFloat(price),
        duration: parseInt(duration, 10),
      })
      setOpen(false)
      setName(""); setPrice(""); setDuration("")
      fetchServices()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

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
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger render={<Button />}>
            + Novo Serviço
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Novo Serviço</DialogTitle>
            </DialogHeader>
            <form onSubmit={handleCreate} className="space-y-4 py-2">
              <div className="space-y-1">
                <Label htmlFor="s-name">Nome *</Label>
                <Input id="s-name" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div className="space-y-1">
                <Label htmlFor="s-price">Preço (R$) *</Label>
                <Input
                  id="s-price"
                  type="number"
                  min="0"
                  step="0.01"
                  value={price}
                  onChange={(e) => setPrice(e.target.value)}
                  required
                  placeholder="50.00"
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="s-duration">Duração (min) *</Label>
                <Input
                  id="s-duration"
                  type="number"
                  min="1"
                  value={duration}
                  onChange={(e) => setDuration(e.target.value)}
                  required
                  placeholder="30"
                />
              </div>
              {error && <p className="text-sm text-destructive">{error}</p>}
              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setOpen(false)}>Cancelar</Button>
                <Button type="submit" disabled={saving}>{saving ? "Salvando…" : "Criar"}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {loading ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : (
        <div className="rounded-md border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
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
                  <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                    Nenhum serviço cadastrado.
                  </TableCell>
                </TableRow>
              )}
              {services.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium">{s.name}</TableCell>
                  <TableCell>{formatBRL(s.price)}</TableCell>
                  <TableCell>{s.duration} min</TableCell>
                  <TableCell>
                    <ActiveBadge active={s.active} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => toggleActive(s)}
                    >
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
