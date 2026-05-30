"use client"

import { useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { api } from "@/lib/api"
import type { Customer } from "@/types"
import { StatusBadge } from "@/components/status-badge"
import { EmptyState } from "@/components/empty-state"
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
import { Search } from "lucide-react"

// --- Edit Dialog ---
function EditCustomerDialog({ customer, onUpdated }: { customer: Customer; onUpdated: () => void }) {
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState(customer.name)
  const [phone, setPhone] = useState(customer.phone)
  const [email, setEmail] = useState(customer.email ?? "")
  const [notes, setNotes] = useState(customer.notes ?? "")

  function handleOpenChange(v: boolean) {
    if (v) {
      setName(customer.name)
      setPhone(customer.phone)
      setEmail(customer.email ?? "")
      setNotes(customer.notes ?? "")
      setError(null)
    }
    setOpen(v)
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.patch(`/customers/${customer.id}`, {
        name,
        phone,
        email: email || null,
        notes: notes || null,
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
        <DialogHeader><DialogTitle>Editar Cliente</DialogTitle></DialogHeader>
        <form onSubmit={handleSave} className="space-y-4 py-2">
          <div className="space-y-1">
            <Label htmlFor="ec-name">Nome *</Label>
            <Input id="ec-name" value={name} onChange={(e) => setName(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-phone">Telefone *</Label>
            <Input id="ec-phone" value={phone} onChange={(e) => setPhone(e.target.value)} required />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-email">E-mail</Label>
            <Input id="ec-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ec-notes">Observações</Label>
            <Textarea
              id="ec-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Preferências, alergias, observações…"
            />
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
export default function CustomersPage() {
  const router = useRouter()
  const [customers, setCustomers] = useState<Customer[]>([])
  const [loading, setLoading] = useState(true)
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState("")

  const [name, setName] = useState("")
  const [phone, setPhone] = useState("")
  const [email, setEmail] = useState("")

  async function fetchCustomers() {
    try {
      const data = await api.get<Customer[]>("/customers/")
      setCustomers(data)
    } catch {
      setError("Erro ao carregar clientes.")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchCustomers() }, [])

  const filtered = customers.filter((c) =>
    c.name.toLowerCase().includes(q.toLowerCase()) || c.phone.includes(q)
  )

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      await api.post("/customers/", { name, phone, email: email || undefined })
      setOpen(false)
      setName(""); setPhone(""); setEmail("")
      fetchCustomers()
    } catch (err: unknown) {
      setError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-3xl tracking-wide">Clientes</h1>
          <p className="text-sm text-muted-foreground">{customers.length} cadastrados</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar por nome ou telefone" className="pl-9" />
          </div>
          <Dialog open={open} onOpenChange={setOpen}>
            <DialogTrigger render={<Button />}>+ Novo Cliente</DialogTrigger>
            <DialogContent>
              <DialogHeader><DialogTitle>Novo Cliente</DialogTitle></DialogHeader>
              <form onSubmit={handleCreate} className="space-y-4 py-2">
                <div className="space-y-1">
                  <Label htmlFor="c-name">Nome *</Label>
                  <Input id="c-name" value={name} onChange={(e) => setName(e.target.value)} required />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="c-phone">Telefone *</Label>
                  <Input id="c-phone" value={phone} onChange={(e) => setPhone(e.target.value)} required placeholder="(11) 99999-9999" />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="c-email">E-mail (opcional)</Label>
                  <Input id="c-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
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
      </div>

      {loading ? (
        <p className="text-muted-foreground">Carregando…</p>
      ) : (
        <div className="rounded-md border border-border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Nome</TableHead>
                <TableHead>Telefone</TableHead>
                <TableHead>E-mail</TableHead>
                <TableHead>Status</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="p-0">
                    <EmptyState message={q ? "Nenhum cliente encontrado." : "Nenhum cliente cadastrado."} />
                  </TableCell>
                </TableRow>
              )}
              {filtered.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-primary/15 text-xs font-medium text-primary flex items-center justify-center flex-shrink-0 select-none">
                        {c.name.split(" ").slice(0, 2).map((p) => p[0]?.toUpperCase()).join("")}
                      </div>
                      <div>
                        <div>{c.name}</div>
                        {c.notes && (
                          <div className="text-xs text-muted-foreground mt-0.5 max-w-xs truncate line-clamp-1">{c.notes}</div>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="font-mono text-sm">{c.phone}</TableCell>
                  <TableCell>{c.email ?? "—"}</TableCell>
                  <TableCell><StatusBadge active={c.active} /></TableCell>
                  <TableCell className="text-right space-x-1">
                    <EditCustomerDialog customer={c} onUpdated={fetchCustomers} />
                    <Button size="sm" variant="outline" onClick={() => router.push(`/customers/${c.id}`)}>
                      Histórico
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
